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
    # Explicit YYYY-MM. Set by the card-statement PDF parser so every charge lands
    # in the month you pay the statement, regardless of its purchase date. When
    # None, the pipeline derives the period from `date`.
    period: str | None = None


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


# --- ICBC credit card, PDF statement (VISA) --------------------------------
# The bank's CSV export is unreliable, so we read the official statement PDF.
# A charge line looks like:
#   19.06.26 002295* GRAELLS NELSON        C.01/06        30.000,00
#   28.05.26 984659  GOOGLE *Google...     USD    1,99    1,99
# The 6-digit voucher after the date is what tells a real purchase apart from
# taxes/fees/payments (those have text, not a voucher, after the date).

_VISA_TXN_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})\s+(\d{6})\*?\s+(.+)$")
_VISA_CUOTA_RE = re.compile(r"\bC\.(\d{2})/(\d{2})\b")
# The "USD" currency marker can be glued to the auth code (e.g. "...TB USD" vs
# "...in1TknlTBUSD"), so match it as a substring, not a whole word. No ARS
# merchant in the statement contains "USD".
_USD_MARK_RE = re.compile(r"USD")
# Argentine money with a trailing '-' meaning a credit (payment/refund).
_MONEY_SIGN_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})(-?)")
# A second "date voucher" inside one line: pypdf sometimes emits a charge twice.
_VISA_DUP_RE = re.compile(r"\d{2}\.\d{2}\.\d{2}\s+\d{6}")


def _visa_statement_period(text: str) -> str | None:
    """The month you pay this statement: the latest dd.mm.yy in the body, which
    is the closing/tax date. All charges get assigned to it."""
    dates = []
    for mo in re.finditer(r"\b(\d{2})\.(\d{2})\.(\d{2})\b", text):
        d, m, y = (int(g) for g in mo.groups())
        try:
            dates.append(date(2000 + y, m, d))
        except ValueError:
            continue
    if not dates:
        return None
    top = max(dates)
    return f"{top.year:04d}-{top.month:02d}"


def parse_card_icbc_pdf(text: str, usd_rate: Decimal | None = None) -> list[NormalizedRow]:
    """Parse an ICBC credit-card statement PDF, auto-detecting VISA vs MASTER."""
    if "MASTERCARD" in text.upper() or "DETALLE DEL MES" in text.upper():
        return _parse_master_pdf(text, usd_rate)
    return _parse_visa_pdf(text, usd_rate)


def _parse_visa_pdf(text: str, usd_rate: Decimal | None = None) -> list[NormalizedRow]:
    """Parse the text of an ICBC VISA statement PDF into charge rows.

    Skips payments, refunds, taxes and fees; keeps real purchases (each with a
    6-digit voucher). USD charges are valued with `usd_rate` (0 for review when
    absent). Every charge is stamped with the statement period so it counts in
    the month the statement is paid, not its purchase month.
    """
    period = _visa_statement_period(text)
    rows: list[NormalizedRow] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = " ".join(raw.split())
        m = _VISA_TXN_RE.match(line)
        if not m:
            continue
        dd, mm, yy, comp, rest = m.groups()
        # A duplicated line concatenates the same charge twice: keep the first.
        dup = _VISA_DUP_RE.search(rest)
        if dup:
            rest = rest[: dup.start()]
        try:
            txn_date = date(2000 + int(yy), int(mm), int(dd))
        except ValueError:
            continue

        cuota = _VISA_CUOTA_RE.search(rest)
        cur, total = (int(cuota.group(1)), int(cuota.group(2))) if cuota else (None, None)

        moneys = _MONEY_SIGN_RE.findall(rest)
        if not moneys:
            continue

        detail = _MONEY_SIGN_RE.sub("", rest)
        detail = _VISA_CUOTA_RE.sub("", detail)
        detail = _USD_MARK_RE.sub("", detail)
        merchant = clean_merchant(" ".join(detail.split()))

        if _USD_MARK_RE.search(rest):
            usd = parse_ar_amount(moneys[0][0])
            if usd == 0:
                continue
            amount = (-usd * usd_rate).quantize(Decimal("0.01")) if usd_rate else Decimal("0")
            description = f"{merchant} (US$ {usd})"
        else:
            num, sign = moneys[-1]  # pesos column
            ars = parse_ar_amount(num)
            if sign == "-" or ars == 0:
                continue  # payment / refund / bonificación, not a purchase
            amount = -ars
            description = merchant

        external_id = f"card:{comp}:{amount}"
        if external_id in seen:
            continue
        seen.add(external_id)
        rows.append(
            NormalizedRow(
                date=txn_date,
                amount=amount,
                description=description,
                external_id=external_id,
                installments_current=cur,
                installments_total=total,
                needs_review=True,
                period=period,
            )
        )
    return rows


# --- ICBC credit card, PDF statement (MASTER) ------------------------------
# A different, messier layout. A charge line looks like:
#   20-Nov-25 AIRBNB * HMECXCM(GBR,USD,   182,59) 00072            182,59
#   18-Nov-25 SEGURO00/0300103578011 00305        10.923,83
#   26-Ago-25 MALLICBC.COM.AR              03/12 00900    47.476,41
# i.e. DD-Mmm-YY <merchant> [NN/NN cuota] <5-digit coupon> <amount>. USD charges
# carry "USD" (in a parenthetical) and their amount is the dollar figure.

_ES_MONTH_ABBR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}  # fmt: skip
# MASTER amounts may omit the thousands separator ("10923,83", not "10.923,83").
_MASTER_TXN_RE = re.compile(
    r"^(\d{2})-([A-Za-z]{3})-(\d{2})\s+(?P<body>.+?)\s+(\d{5})\s+(?P<amount>\d[\d.]*,\d{2})\s*$"
)
_MASTER_CUOTA_RE = re.compile(r"(?:^|\s)(\d{2})/(\d{2})(?=\s|$)")
_PARENS_RE = re.compile(r"\([^)]*\)")


def _next_month_period(d: date) -> str:
    """The month you pay a statement: the month after its latest charge."""
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return f"{year:04d}-{month:02d}"


def _parse_master_pdf(text: str, usd_rate: Decimal | None = None) -> list[NormalizedRow]:
    """Parse the text of an ICBC MASTERCARD statement PDF into charge rows.

    Same output contract as the VISA parser: purchases only (payments/taxes have
    no coupon and are skipped), USD valued with `usd_rate`, every charge stamped
    with the statement period (the month after the latest charge).
    """
    parsed = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        m = _MASTER_TXN_RE.match(line)
        if not m:
            continue
        month = _ES_MONTH_ABBR.get(m.group(2).lower())
        if not month:
            continue
        try:
            txn_date = date(2000 + int(m.group(3)), month, int(m.group(1)))
        except ValueError:
            continue
        parsed.append((txn_date, m.group("body"), m.group(5), m.group("amount")))

    if not parsed:
        return []
    period = _next_month_period(max(p[0] for p in parsed))

    rows: list[NormalizedRow] = []
    seen: set[str] = set()
    for txn_date, body, coupon, amount_str in parsed:
        cuota = _MASTER_CUOTA_RE.search(body)
        cur, total = (int(cuota.group(1)), int(cuota.group(2))) if cuota else (None, None)

        detail = _MASTER_CUOTA_RE.sub(" ", body)
        detail = _PARENS_RE.sub(" ", detail)  # drop "(GBR,USD, 182,59)"
        detail = _MONEY_SIGN_RE.sub("", detail)
        merchant = clean_merchant(" ".join(detail.split()))

        value = parse_ar_amount(amount_str)
        if value == 0:
            continue
        if "USD" in body.upper():
            amount = (-value * usd_rate).quantize(Decimal("0.01")) if usd_rate else Decimal("0")
            description = f"{merchant} (US$ {value})"
        else:
            amount = -value
            description = merchant

        external_id = f"card:{coupon}:{amount}"
        if external_id in seen:
            continue
        seen.add(external_id)
        rows.append(
            NormalizedRow(
                date=txn_date,
                amount=amount,
                description=description,
                external_id=external_id,
                installments_current=cur,
                installments_total=total,
                needs_review=True,
                period=period,
            )
        )
    return rows


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from a PDF. Raises ParseError if it can't be read."""
    from io import BytesIO

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ParseError("Falta la librería para leer PDF (pypdf).") from exc
    try:
        reader = PdfReader(BytesIO(file_bytes))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ParseError("No se pudo leer el PDF (¿está protegido o dañado?).") from exc


def parse_csv(
    file_bytes: bytes, source: str | None = None, usd_rate: Decimal | None = None
) -> list[NormalizedRow]:
    """Parse an uploaded file into normalized rows, dispatching by source.

    Accepts the ICBC card statement as PDF (the bank's CSV export is unreliable);
    everything else is CSV.
    """
    if file_bytes[:5] == b"%PDF-":
        if source == "card_icbc":
            return parse_card_icbc_pdf(extract_pdf_text(file_bytes), usd_rate)
        raise ParseError("El PDF solo se admite como resumen de tarjeta ICBC. Elegí esa fuente.")
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
