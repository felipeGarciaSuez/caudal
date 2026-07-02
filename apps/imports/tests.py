from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse

from apps.imports.models import CategoryRule, ImportBatch
from apps.imports.parsers import (
    ParseError,
    clean_merchant,
    parse_ar_amount,
    parse_bank_icbc,
    parse_card_icbc,
    parse_csv,
    parse_date,
)
from apps.imports.services import MAX_IMPORT_ROWS, _shift_one_month, run_import
from apps.transactions.models import Category, Transaction
from apps.wallets.models import Wallet

pytestmark = pytest.mark.django_db


# --- pure parsing (no DB) --------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.234,56", Decimal("1234.56")),
        ("-1.234,56", Decimal("-1234.56")),
        ("$ 1.234,56", Decimal("1234.56")),
        ("(1.234,56)", Decimal("-1234.56")),
        ("1234.56", Decimal("1234.56")),
        ("2.000", Decimal("2000")),
        ("0,50", Decimal("0.50")),
        ("-500", Decimal("-500")),
    ],
)
def test_parse_ar_amount(raw, expected):
    assert parse_ar_amount(raw) == expected


@pytest.mark.parametrize(
    "raw,iso",
    [
        ("15/06/2026", "2026-06-15"),
        ("2026-06-15", "2026-06-15"),
        ("15-06-2026", "2026-06-15"),
        ("2026-06-15T13:45:00", "2026-06-15"),
    ],
)
def test_parse_date(raw, iso):
    assert parse_date(raw).isoformat() == iso


def test_parse_csv_detects_columns_and_signs():
    # es-AR exports use ';' so the decimal comma doesn't clash with the delimiter.
    content = (
        "Fecha;Descripción;Monto\n"
        "15/06/2026;Compra RAPPI;-3.500,50\n"
        "16/06/2026;Sueldo;1.900.000,00\n"
    ).encode()
    rows = parse_csv(content)
    assert len(rows) == 2
    assert rows[0].description == "Compra RAPPI"
    assert rows[0].amount == Decimal("-3500.50")
    assert rows[1].amount == Decimal("1900000.00")


def test_parse_csv_us_style_comma_delimiter():
    # US-style export: ',' delimiter with '.' decimals.
    content = b"Fecha,Descripcion,Monto\n15/06/2026,Coffee shop,-3.50\n"
    rows = parse_csv(content)
    assert len(rows) == 1
    assert rows[0].amount == Decimal("-3.50")


def test_parse_csv_semicolon_delimiter():
    content = b"fecha;detalle;importe\n01/07/2026;Kiosco;-1.200,00\n"
    rows = parse_csv(content)
    assert len(rows) == 1
    assert rows[0].amount == Decimal("-1200.00")


def test_parse_csv_missing_columns_raises():
    with pytest.raises(ParseError):
        parse_csv(b"col_a,col_b\n1,2\n")


# --- import service (DB) ---------------------------------------------------


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="felipe", password="x")


@pytest.fixture
def wallet(user):
    return Wallet.objects.create(owner=user, name="Mercado Pago", kind=Wallet.Kind.WALLET)


def _csv(rows):
    # Semicolon-delimited to match es-AR exports (comma is the decimal separator).
    header = "Fecha;Descripción;Monto\n"
    body = "".join(rows)
    return BytesIO((header + body).encode("utf-8"))


def test_run_import_creates_transactions_with_kinds(user, wallet):
    f = _csv(
        [
            "15/06/2026;Compra kiosco;-1.200,00\n",
            "16/06/2026;Transferencia recibida;5.000,00\n",
        ]
    )
    result = run_import(owner=user, wallet=wallet, source="mercadopago", file=f)
    assert result.rows_imported == 2
    expense = Transaction.objects.get(kind=Transaction.Kind.EXPENSE)
    income = Transaction.objects.get(kind=Transaction.Kind.INCOME)
    assert expense.amount == Decimal("1200.00")  # stored positive
    assert expense.source == Transaction.Source.IMPORT
    assert income.amount == Decimal("5000.00")
    assert expense.period == "2026-06"


def test_run_import_rejects_too_many_rows(user, wallet):
    # A file over the ceiling must be refused before any INSERT (DoS guard).
    rows = [
        f"{(i % 28) + 1:02d}/06/2026;Gasto {i};-{i + 1},00\n" for i in range(MAX_IMPORT_ROWS + 1)
    ]
    with pytest.raises(ParseError):
        run_import(owner=user, wallet=wallet, source="mercadopago", file=_csv(rows))
    assert Transaction.objects.count() == 0


def test_run_import_dedupes_on_reimport(user, wallet):
    rows = ["15/06/2026;Compra kiosco;-1.200,00\n"]
    run_import(owner=user, wallet=wallet, source="mercadopago", file=_csv(rows))
    result = run_import(owner=user, wallet=wallet, source="mercadopago", file=_csv(rows))
    assert result.rows_imported == 0
    assert result.rows_skipped == 1
    assert Transaction.objects.count() == 1


def test_run_import_applies_category_rules(user, wallet):
    delivery = Category.objects.create(owner=user, name="Delivery", kind=Category.Kind.ANT)
    CategoryRule.objects.create(owner=user, keyword="RAPPI", category=delivery)
    run_import(
        owner=user,
        wallet=wallet,
        source="mercadopago",
        file=_csv(["10/06/2026;Pago RAPPI*Pedido;-4.800,00\n"]),
    )
    tx = Transaction.objects.get()
    assert tx.category == delivery


def test_run_import_leaves_unmatched_uncategorized(user, wallet):
    run_import(
        owner=user,
        wallet=wallet,
        source="mercadopago",
        file=_csv(["10/06/2026;Algo raro sin regla;-999,00\n"]),
    )
    tx = Transaction.objects.get()
    assert tx.category is None


def test_run_import_records_batch(user, wallet):
    run_import(
        owner=user,
        wallet=wallet,
        source="mercadopago",
        file=_csv(["10/06/2026;X;-100,00\n"]),
    )
    batch = ImportBatch.objects.get()
    assert batch.rows_total == 1
    assert batch.rows_imported == 1
    assert batch.wallet == wallet


# --- ICBC bank (headerless, US date, debit/credit) -------------------------


def test_clean_merchant_strips_prefix_and_gateway():
    assert clean_merchant("CPA. PAYU AR UBER") == "UBER"
    assert clean_merchant("MERPAGO*COTO") == "COTO"
    assert clean_merchant("CPA. DLO RAPPI") == "RAPPI"


def test_parse_bank_icbc_signs_dates_and_transfers():
    text = (
        "06/30/26,TRANS PAG SUEL,0.0,1500000.0,1600000.00\n"
        "06/29/26,CPA. PEDIDOSYA SUSHI POP,4500.0,0.0,100000.00\n"
        "06/18/26,TRANSF. MOBILE,8500.0,0.0,104500.00\n"
    )
    rows = parse_bank_icbc(text)
    assert len(rows) == 3
    assert rows[0].amount == Decimal("1500000.0")  # credit -> income
    assert rows[0].date.isoformat() == "2026-06-30"
    assert rows[0].external_id == "icbc:1600000.00"
    assert rows[1].amount == Decimal("-4500.0")  # debit -> expense
    assert rows[1].description == "PEDIDOSYA SUSHI POP"  # CPA. stripped
    assert rows[2].kind == "transfer"


def test_run_import_bank_marks_transfers(user):
    bank = Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK)
    text = "06/18/26,TRANSF. MOBILE,8500.0,0.0,104500.00\n"
    run_import(owner=user, wallet=bank, source="bank_icbc", file=BytesIO(text.encode()))
    tx = Transaction.objects.get()
    assert tx.kind == Transaction.Kind.TRANSFER


# --- ICBC credit card (sections, cuotas, USD) ------------------------------


def test_parse_card_icbc_cuotas_usd_and_skips_payments():
    text = (
        "  Fecha;Comercio;Comprobante;Importe $;Importe U$S\n"
        "Consumos Tarjeta:0000000000000000\n"
        "19/06/2026;SERVICIO CUOTA 01/06;00000001;30000.0;0.00\n"
        "21/06/2026;ANTHROPIC* CLAUD xx;00000002;0.00;20.0\n"
        "Pagos Tarjeta:\n"
        "10/06/2026;SU PAGO EN PESOS;00000003;-171000.0;0.00\n"
    )
    rows = parse_card_icbc(text, usd_rate=Decimal("1400"))
    assert len(rows) == 2  # the payment line is skipped
    assert rows[0].installments_current == 1
    assert rows[0].installments_total == 6
    assert rows[0].amount == Decimal("-30000.0")
    assert rows[0].needs_review is True
    assert rows[1].amount == Decimal("-28000.00")  # 20 USD * 1400
    assert "US$" in rows[1].description


def test_parse_card_usd_without_rate_is_zero():
    text = "Fecha;Comercio;Comprobante;Importe $;Importe U$S\n21/06/2026;ANTHROPIC;001;0.00;20.0\n"
    rows = parse_card_icbc(text, usd_rate=None)
    assert rows[0].amount == Decimal("0")


def test_run_import_card_sets_review_and_installments(user):
    card = Wallet.objects.create(owner=user, name="ICBC Visa", kind=Wallet.Kind.CREDIT_CARD)
    text = (
        "Fecha;Comercio;Comprobante;Importe $;Importe U$S\n"
        "Consumos Tarjeta:123\n"
        "19/06/2026;SERVICIO CUOTA 01/06;00000001;30000.0;0.00\n"
    )
    run_import(owner=user, wallet=card, source="card_icbc", file=BytesIO(text.encode()))
    tx = Transaction.objects.get()
    assert tx.needs_review is True
    assert tx.installments_current == 1
    assert tx.installments_total == 6
    assert tx.amount == Decimal("30000.0")
    # Billed the following month's statement, not the purchase month.
    assert tx.date.isoformat() == "2026-07-19"
    assert tx.period == "2026-07"


def test_run_import_card_clamps_month_end():
    assert _shift_one_month(date(2026, 1, 31)).isoformat() == "2026-02-28"
    assert _shift_one_month(date(2026, 12, 15)).isoformat() == "2027-01-15"


def test_run_import_bank_icbc_keeps_original_month(user):
    # Only the credit card statement shifts a month forward; the bank account
    # itself reflects real movements as they happen.
    bank = Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK)
    text = "06/29/26,CPA. PEDIDOSYA SUSHI POP,33689.0,0.0,2208.36\n"
    run_import(owner=user, wallet=bank, source="bank_icbc", file=BytesIO(text.encode()))
    tx = Transaction.objects.get()
    assert tx.period == "2026-06"


# --- Review screen ---------------------------------------------------------


@pytest.fixture
def client_logged(client, user):
    client.force_login(user)
    return client


def _card_item(user, amount="10000", **kwargs):
    card, _ = Wallet.objects.get_or_create(
        owner=user, name="ICBC Visa", defaults={"kind": Wallet.Kind.CREDIT_CARD}
    )
    return Transaction.objects.create(
        owner=user,
        wallet=card,
        amount=Decimal(amount),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-10",
        needs_review=True,
        **kwargs,
    )


def test_review_update_confirms_and_sets_share(client_logged, user):
    cat = Category.objects.create(owner=user, name="Súper", kind=Category.Kind.VARIABLE)
    tx = _card_item(user, "10000")
    resp = client_logged.post(
        reverse("imports:review_update", args=[tx.id]),
        {"category": cat.id, "share": "0.500"},
    )
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.needs_review is False
    assert tx.category == cat
    assert tx.shared_ratio == Decimal("0.500")
    assert tx.is_shared is True
    assert tx.own_amount == Decimal("5000.00")


def test_review_confirm_all(client_logged, user):
    for _ in range(3):
        _card_item(user, "100")
    resp = client_logged.post(reverse("imports:review_confirm_all"))
    assert resp.status_code == 200
    assert Transaction.objects.filter(owner=user, needs_review=True).count() == 0


def test_review_delete(client_logged, user):
    tx = _card_item(user, "100")
    resp = client_logged.post(reverse("imports:review_delete", args=[tx.id]))
    assert resp.status_code == 200
    assert Transaction.objects.count() == 0


def test_cannot_review_other_users_item(client_logged, django_user_model):
    other = django_user_model.objects.create_user(username="otro", password="x")
    tx = _card_item(other, "100")
    resp = client_logged.post(reverse("imports:review_delete", args=[tx.id]))
    assert resp.status_code == 404
    assert Transaction.objects.filter(pk=tx.id).exists()
