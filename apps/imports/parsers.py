"""CSV parsing for account exports (Mercado Pago, Ualá, Personal Pay, bank, card).

Strategy: a generic header-alias parser handles well-formed CSVs, and dedicated
parsers handle the quirky real-world layouts of the ICBC bank export (no header,
US date, debit/credit split) and the ICBC credit-card statement (sections,
cuotas, USD charges). Amounts and dates use es-AR conventions.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Header aliases (lowercased, stripped) -> normalized field.
DATE_ALIASES = {
    "fecha",
    "date",
    "transaction_date",
    "fecha de operación",
    "fecha de operacion",
    "fecha operación",
    "fecha operacion",
    "fecha_operacion",
    "día",
    "dia",
    "fecha y hora",
    "fecha contable",
}
AMOUNT_ALIASES = {
    "monto",
    "importe",
    "amount",
    "transaction_amount",
    "valor",
    "value",
    "monto (ars)",
    "importe ($)",
    "débito/crédito",
    "debito/credito",
}
DESC_ALIASES = {
    "descripción",
    "descripcion",
    "detalle",
    "concepto",
    "description",
    "motivo",
    "referencia",
    "nombre",
    "actividad",
    "comercio",
    "tipo de operación",
    "tipo de operacion",
}
ID_ALIASES = {
    "id",
    "source_id",
    "operation_id",
    "número de operación",
    "numero de operacion",
    "id de operación",
    "id de operacion",
    "external_reference",
    "comprobante",
    "número",
    "numero",
}

DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
]

# Bank/card descriptions carry noise prefixes and payment-gateway tokens; the
# real merchant is what's left after stripping them.
_PREFIXES = ("CPA.", "PAGO C/TF QR", "PAGO", "TRANSF.", "TRANSFERENCIA", "BONIF. CONSUMO")
_GATEWAYS = ("PAYU AR", "MERPAGO*", "MERPAGO", "DLO*", "DLO", "FS *", "FS*")

# Bank lines that move money around instead of being real consumption.
_TRANSFER_HINTS = (
    "TRANSF",
    "TRANSFERENCIA",
    "DEBITO INMEDIATO",
    "COMPRA / VENTA DE TITULO",
    "PAGO TARJETA",
    "PAGO VISA",
    "PAGO MASTER",
)

_CUOTA_RE = re.compile(r"\s(\d{2})/(\d{2})\s*$")


@dataclass
class NormalizedRow:
    date: date
    amount: Decimal  # signed: negative = money out (expense), positive = money in
    description: str
    external_id: str | None = None
    kind: str | None = None  # 'expense' | 'income' | 'transfer'; None -> by sign
    installments_current: int | None = None
    installments_total: int | None = None
    needs_review: bool = False


class ParseError(Exception):
    """Raised when a file can't be parsed (bad columns, empty, etc.)."""


def parse_ar_amount(raw: str) -> Decimal:
    """Parse an amount string in es-AR or plain format into a signed Decimal.

    Handles "$ 1.234,56", "-1.234,56", "1234.56", "(1.234,56)" (parenthesised = negative).
    """
    if raw is None:
        raise ParseError("monto vacío")
    s = str(raw).strip()
    if not s:
        raise ParseError("monto vacío")

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    # Strip currency symbols / spaces / non-breaking spaces.
    s = s.replace("$", "").replace("ARS", "").replace("U$S", "").replace("\xa0", "").strip()
    if s.startswith("-"):
        negative = True
        s = s[1:].strip()
    s = s.replace(" ", "")

    # Decide decimal separator. es-AR uses ',' for decimals and '.' for thousands,
    # but US-style exports use '.' for decimals. Disambiguate carefully.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[-1]) == 3):
            s = s.replace(".", "")

    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise ParseError(f"monto inválido: {raw!r}") from exc
    return -value if negative else value


def parse_date(raw: str) -> date:
    s = str(raw).strip()
    if not s:
        raise ParseError("fecha vacía")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s[: len(fmt) + 8], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError as exc:
        raise ParseError(f"fecha inválida: {raw!r}") from exc


def clean_merchant(description: str) -> str:
    """Strip bank prefixes and payment-gateway tokens to expose the merchant.

    "CPA. PAYU AR UBER" -> "UBER"; "MERPAGO*COTO" -> "COTO". The result still
    contains the merchant name, so keyword categorization keeps working.
    """
    s = " ".join((description or "").split())
    upper = s.upper()
    for pfx in _PREFIXES:
        if upper.startswith(pfx):
            s = s[len(pfx) :].strip()
            upper = s.upper()
            break
    for gw in _GATEWAYS:
        if upper.startswith(gw):
            s = s[len(gw) :].lstrip(" *")
            break
    return s.strip() or (description or "").strip()


def _split_installments(description: str) -> tuple[str, int | None, int | None]:
    """Pull a trailing 'NN/MM' cuota marker off a card merchant string."""
    match = _CUOTA_RE.search(description)
    if not match:
        return description, None, None
    current, total = int(match.group(1)), int(match.group(2))
    cleaned = description[: match.start()].strip()
    return cleaned, current, total


# --- Generic (header-based) --------------------------------------------------


def _match_columns(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    normalized = {h: h.strip().lower() for h in headers}

    def find(aliases: set[str], contains: list[str]) -> str | None:
        for original, low in normalized.items():
            if low in aliases:
                return original
        for original, low in normalized.items():
            if any(token in low for token in contains):
                return original
        return None

    mapping["date"] = find(DATE_ALIASES, ["fecha", "date"])
    mapping["amount"] = find(AMOUNT_ALIASES, ["monto", "importe", "amount", "valor"])
    mapping["description"] = find(
        DESC_ALIASES, ["desc", "detalle", "concepto", "motivo", "referencia", "comercio"]
    )
    mapping["external_id"] = find(ID_ALIASES, ["id", "operaci", "comprobante", "número", "numero"])
    return mapping


def _parse_generic(text: str) -> list[NormalizedRow]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ParseError("no se detectaron columnas")

    cols = _match_columns(list(reader.fieldnames))
    if not cols["date"] or not cols["amount"]:
        raise ParseError(
            f"no se encontraron columnas de fecha y monto. Columnas detectadas: {reader.fieldnames}"
        )

    rows: list[NormalizedRow] = []
    for raw in reader:
        raw_amount = raw.get(cols["amount"])
        raw_date = raw.get(cols["date"])
        if not raw_date and not raw_amount:
            continue
        try:
            parsed_date = parse_date(raw_date)
            amount = parse_ar_amount(raw_amount)
        except ParseError:
            continue
        if amount == 0:
            continue
        description = (raw.get(cols["description"]) or "").strip() if cols["description"] else ""
        external_id = (raw.get(cols["external_id"]) or "").strip() if cols["external_id"] else ""
        rows.append(
            NormalizedRow(
                date=parsed_date,
                amount=amount,
                description=clean_merchant(description),
                external_id=external_id or None,
            )
        )
    return rows


# --- ICBC bank export (no header; date, desc, debit, credit, balance) --------


def parse_bank_icbc(text: str) -> list[NormalizedRow]:
    rows: list[NormalizedRow] = []
    reader = csv.reader(io.StringIO(text))
    for fields in reader:
        if len(fields) < 5:
            continue
        raw_date, raw_desc, raw_debit, raw_credit, raw_balance = fields[:5]
        try:
            parsed_date = datetime.strptime(raw_date.strip(), "%m/%d/%y").date()
            debit = parse_ar_amount(raw_debit)
            credit = parse_ar_amount(raw_credit)
        except (ParseError, ValueError):
            continue  # header/garbage lines
        amount = credit - debit  # money in positive, money out negative
        if amount == 0:
            continue
        desc = raw_desc.strip()
        upper = desc.upper()
        kind = "transfer" if any(h in upper for h in _TRANSFER_HINTS) else None
        rows.append(
            NormalizedRow(
                date=parsed_date,
                amount=amount,
                description=clean_merchant(desc),
                # The running balance uniquely identifies each row in the account.
                external_id=f"icbc:{raw_balance.strip()}",
                kind=kind,
            )
        )
    return rows


# --- ICBC credit-card statement ----------------------------------------------


def parse_card_icbc(text: str, usd_rate: Decimal | None = None) -> list[NormalizedRow]:
    """Parse the ICBC card statement.

    Sections: 'Consumos Tarjeta' (charges) and 'Pagos Tarjeta' (the payments you
    made, which are NOT consumption and are skipped). USD charges are converted
    with `usd_rate` when available; otherwise they come in at 0 for review, with
    the USD figure kept in the description.
    """
    rows: list[NormalizedRow] = []
    in_payments = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith("pagos tarjeta"):
            in_payments = True
            continue
        if low.startswith("consumos tarjeta"):
            in_payments = False
            continue
        if in_payments:
            continue  # su pago en pesos/usd -> settlement, not a new expense
        fields = stripped.split(";")
        if len(fields) < 5:
            continue
        raw_date, comercio, comprobante, raw_ars, raw_usd = (f.strip() for f in fields[:5])
        if raw_date.lower().startswith("fecha"):
            continue  # header row
        try:
            parsed_date = parse_date(raw_date)
        except ParseError:
            continue
        try:
            ars = parse_ar_amount(raw_ars) if raw_ars else Decimal("0")
        except ParseError:
            ars = Decimal("0")
        try:
            usd = parse_ar_amount(raw_usd) if raw_usd else Decimal("0")
        except ParseError:
            usd = Decimal("0")

        merchant, cur, total = _split_installments(comercio)
        description = clean_merchant(merchant)

        if ars != 0:
            amount = -ars  # a positive charge is money out
        elif usd != 0:
            if usd_rate:
                amount = (-usd * usd_rate).quantize(Decimal("0.01"))
            else:
                amount = Decimal("0")  # unknown ARS until a dollar price is set
            description = f"{description} (US$ {usd})"
        else:
            continue

        rows.append(
            NormalizedRow(
                date=parsed_date,
                amount=amount,
                description=description,
                external_id=f"card:{comprobante}:{amount}",
                installments_current=cur,
                installments_total=total,
                needs_review=True,  # the card is never taken at face value
            )
        )
    return rows


def parse_csv(
    file_bytes: bytes, source: str | None = None, usd_rate: Decimal | None = None
) -> list[NormalizedRow]:
    """Parse CSV bytes into normalized rows, dispatching by source."""
    text = _decode(file_bytes)
    if not text.strip():
        raise ParseError("el archivo está vacío")
    if source == "bank_icbc":
        return parse_bank_icbc(text)
    if source == "card_icbc":
        return parse_card_icbc(text, usd_rate)
    return _parse_generic(text)


def _decode(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")
