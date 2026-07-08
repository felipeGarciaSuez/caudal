"""Import orchestration: parse -> dedupe -> categorize -> persist."""

from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass
from datetime import date

from django.db import transaction as db_transaction

from apps.savings.services import current_dollar_price
from apps.transactions.models import Transaction

from .models import CategoryRule, ImportBatch
from .parsers import NormalizedRow, ParseError, parse_csv

# Hard ceiling on rows per import. A single request must never turn into tens of
# thousands of INSERTs: on the free tier that ties up the only worker (effective
# DoS) and bloats the DB. Real monthly exports are well under this.
MAX_IMPORT_ROWS = 2000


@dataclass
class ImportResult:
    batch: ImportBatch
    rows_total: int
    rows_imported: int
    rows_skipped: int


def _shift_one_month(d: date) -> date:
    """Same day next month, clamped to month length.

    A credit-card statement bills what you spent last month: a charge dated in
    June only hits your wallet (and your budget) when you pay the July
    statement. So card rows land one period ahead of their purchase date.
    """
    year, month = d.year, d.month + 1
    if month > 12:
        month = 1
        year += 1
    last_day = calendar.monthrange(year, month)[1]
    return d.replace(year=year, month=month, day=min(d.day, last_day))


def _dedupe_key(wallet_id: int, row: NormalizedRow) -> str:
    """Stable external_id used to catch re-imports.

    Uses the source id when present; otherwise a hash of date+amount+description.
    """
    if row.external_id:
        return row.external_id[:120]
    raw = f"{wallet_id}|{row.date}|{row.amount}|{row.description}".lower()
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    return f"h:{digest}"


class _Categorizer:
    """Applies the owner's keyword rules to a description."""

    def __init__(self, owner):
        self.rules = list(
            CategoryRule.objects.filter(owner=owner, is_active=True)
            .select_related("category")
            .order_by("priority", "id")
        )

    def categorize(self, description: str):
        low = (description or "").lower()
        for rule in self.rules:
            if rule.keyword.lower() in low:
                return rule.category
        return None


def _read_file(file) -> tuple[bytes, object | None]:
    """Return (bytes, stored_file). `file` may be an uploaded file or raw bytes;
    stored_file is the uploaded file to keep on the batch, or None for bytes."""
    if hasattr(file, "read"):
        file_bytes = file.read()
        if hasattr(file, "seek"):
            file.seek(0)  # rewind so it can be stored on the batch
        return file_bytes, (file if getattr(file, "name", None) else None)
    return file, None


def prepare_import(
    *, owner, wallet, source: str, file_bytes: bytes
) -> tuple[list[Transaction], int, int]:
    """Parse and dedupe an import into unsaved Transaction rows. No DB writes.

    Returns (to_create, rows_total, skipped). Raises ParseError on a bad file.
    This is the preview step; `commit_import` persists the result.
    """
    is_card = source == ImportBatch.Source.CARD_ICBC
    # USD card charges are valued with the manual dollar price (fase 4).
    usd_rate = current_dollar_price(owner) if is_card else None
    rows = parse_csv(file_bytes, source=source, usd_rate=usd_rate)  # may raise ParseError
    if len(rows) > MAX_IMPORT_ROWS:
        raise ParseError(
            f"El archivo tiene demasiados movimientos ({len(rows)}). "
            f"El máximo por importación es {MAX_IMPORT_ROWS}. Dividilo en partes más chicas."
        )
    if is_card:
        for row in rows:
            # The PDF statement already carries its own period (the month it's
            # paid); only the CSV export needs its purchase dates shifted forward.
            if row.period is None:
                row.date = _shift_one_month(row.date)

    categorizer = _Categorizer(owner)

    # Existing dedupe keys already in this wallet.
    existing = set(
        Transaction.objects.filter(wallet=wallet, external_id__isnull=False).values_list(
            "external_id", flat=True
        )
    )
    seen_in_file: set[str] = set()

    to_create: list[Transaction] = []
    skipped = 0
    for row in rows:
        key = _dedupe_key(wallet.id, row)
        if key in existing or key in seen_in_file:
            skipped += 1
            continue
        seen_in_file.add(key)

        # Kind: the parser may force 'transfer'; otherwise sign decides.
        if row.kind:
            kind = row.kind
        else:
            kind = Transaction.Kind.INCOME if row.amount > 0 else Transaction.Kind.EXPENSE
        category = (
            categorizer.categorize(row.description) if kind == Transaction.Kind.EXPENSE else None
        )
        to_create.append(
            Transaction(
                owner=owner,
                date=row.date,
                amount=abs(row.amount),
                kind=kind,
                wallet=wallet,
                category=category,
                description=row.description,
                is_paid=True,
                source=Transaction.Source.IMPORT,
                external_id=key,
                installments_current=row.installments_current,
                installments_total=row.installments_total,
                needs_review=row.needs_review,
                # bulk_create bypasses Transaction.save(), so set the denormalised
                # YYYY-MM period here (save() would otherwise derive it from date).
                # A card-statement PDF pins an explicit period; else derive from date.
                period=row.period or str(row.date)[:7],
            )
        )
    return to_create, len(rows), skipped


def commit_import(*, batch: ImportBatch, to_create: list[Transaction]) -> ImportResult:
    """Persist prepared rows against `batch` and mark it confirmed."""
    with db_transaction.atomic():
        for tx in to_create:
            tx.import_batch = batch
        batch.rows_imported = len(to_create)
        batch.confirmed = True
        batch.save(update_fields=["rows_imported", "confirmed"])
        Transaction.objects.bulk_create(to_create)
    return ImportResult(
        batch=batch,
        rows_total=batch.rows_total,
        rows_imported=len(to_create),
        rows_skipped=batch.rows_skipped,
    )


def run_import(*, owner, wallet, source: str, file) -> ImportResult:
    """Parse and import in one shot (no preview). Kept for tests/programmatic use."""
    file_bytes, stored_file = _read_file(file)
    to_create, rows_total, skipped = prepare_import(
        owner=owner, wallet=wallet, source=source, file_bytes=file_bytes
    )
    batch = ImportBatch(
        owner=owner, wallet=wallet, source=source, rows_total=rows_total, rows_skipped=skipped
    )
    if stored_file is not None:
        batch.file = stored_file
    batch.save()
    return commit_import(batch=batch, to_create=to_create)


__all__ = ["prepare_import", "commit_import", "run_import", "ImportResult", "ParseError"]
