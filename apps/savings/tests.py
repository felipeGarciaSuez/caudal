from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budgets.models import MonthlyBudget
from apps.savings import services
from apps.savings.models import Asset, PriceSnapshot, SavingsMovement
from apps.transactions.models import Category, Transaction
from apps.wallets.models import Wallet

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="felipe", password="x")


@pytest.fixture
def client_logged(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def wallet(user):
    return Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK)


@pytest.fixture
def usd():
    return Asset.objects.create(symbol="USD", name="Dólar billete", kind=Asset.Kind.FIAT_CASH)


@pytest.fixture
def usdt():
    return Asset.objects.create(symbol="USDT", name="Dólar cripto", kind=Asset.Kind.STABLECOIN)


def _buy(user, asset, qty, ars, when, *, wallet=None, location=""):
    return SavingsMovement.objects.create(
        owner=user,
        date=when,
        kind=SavingsMovement.Kind.BUY,
        asset=asset,
        quantity=Decimal(qty),
        ars_amount=Decimal(ars),
        from_wallet=wallet,
        location=location,
    )


def _sell(user, asset, qty, ars, when, *, wallet=None, location=""):
    return SavingsMovement.objects.create(
        owner=user,
        date=when,
        kind=SavingsMovement.Kind.SELL,
        asset=asset,
        quantity=Decimal(qty),
        ars_amount=Decimal(ars),
        from_wallet=wallet,
        location=location,
    )


def test_movement_derives_period_and_unit_price(user, usd, wallet):
    mv = _buy(user, usd, "100", "135000", date(2026, 7, 10), wallet=wallet)
    assert mv.period == "2026-07"
    assert mv.unit_price == Decimal("1350.00")


def test_portfolio_aggregates_quantity_and_locations(user, usd, usdt):
    _buy(user, usd, "100", "135000", date(2026, 6, 1), location="Colchón")
    _buy(user, usd, "50", "70000", date(2026, 7, 1), location="Colchón")
    _buy(user, usd, "30", "42000", date(2026, 7, 3), location="Caja fuerte")
    _buy(user, usdt, "200", "280000", date(2026, 7, 5), location="Belo")

    portfolio = services.build_portfolio(user)
    assert portfolio["total_usd"] == Decimal("380")  # 180 USD + 200 USDT

    by_symbol = {r["asset"].symbol: r for r in portfolio["rows"]}
    assert by_symbol["USD"]["qty"] == Decimal("180")
    locations = dict(by_symbol["USD"]["locations"])
    assert locations["Colchón"] == Decimal("150")
    assert locations["Caja fuerte"] == Decimal("30")


def test_portfolio_valuation_and_pnl(user, usd):
    # Bought 100 USD for 100.000 ARS -> avg 1000/USD.
    _buy(user, usd, "100", "100000", date(2026, 6, 1), location="Colchón")
    PriceSnapshot.objects.create(asset=usd, price_ars=Decimal("1200"))

    portfolio = services.build_portfolio(user)
    row = portfolio["rows"][0]
    assert row["avg_price"] == Decimal("1000.00")
    assert row["value_ars"] == Decimal("120000.00")
    assert row["pnl_ars"] == Decimal("20000.00")
    assert portfolio["total_value_ars"] == Decimal("120000.00")
    assert portfolio["has_price"] is True


def test_portfolio_without_price_has_no_value(user, usd):
    _buy(user, usd, "100", "100000", date(2026, 6, 1))
    portfolio = services.build_portfolio(user)
    assert portfolio["has_price"] is False
    assert portfolio["total_value_ars"] is None
    assert portfolio["rows"][0]["value_ars"] is None


def test_saved_ars_ignores_buys_entirely(user, usd, wallet):
    # Buys no longer discount here — they create a real "Ahorro" expense
    # instead (see the create_ahorro_expense tests below).
    _buy(user, usd, "100", "135000", date(2026, 7, 5), wallet=wallet)
    _buy(user, usd, "50", "70000", date(2026, 7, 8))
    assert services.saved_ars(user, "2026-07") == Decimal("0.00")


def test_create_ahorro_expense_links_and_categorizes(user, wallet, usd):
    mv = _buy(user, usd, "100", "135000", date(2026, 7, 5), wallet=wallet)
    tx = services.create_ahorro_expense(mv)
    mv.refresh_from_db()
    assert mv.linked_expense_id == tx.id
    assert tx.category.name == "Ahorro"
    assert tx.category.kind == Category.Kind.VARIABLE
    assert tx.amount == Decimal("135000.00")
    assert tx.wallet == wallet
    assert tx.kind == Transaction.Kind.EXPENSE
    assert tx.source == Transaction.Source.MANUAL


def test_remaining_discounts_ahorro_expense(user, wallet, usd):
    budget = MonthlyBudget.objects.create(
        owner=user, period="2026-07", expected_income=Decimal("1800000")
    )
    mv = _buy(user, usd, "100", "135000", date(2026, 7, 5), wallet=wallet)
    services.create_ahorro_expense(mv)
    assert budget.total_spent == Decimal("135000.00")
    assert budget.total_saved == Decimal("0.00")  # no net sell this period
    assert budget.remaining == Decimal("1665000.00")


def test_add_movement_buy_with_wallet_creates_ahorro_expense(client_logged, user, wallet, usd):
    resp = client_logged.post(
        reverse("savings:add_movement"),
        {
            "asset": usd.id,
            "quantity": "100",
            "ars_amount": "135.000",
            "date": "2026-07-05",
            "location": "Colchón",
            "from_wallet": wallet.id,
        },
    )
    assert resp.status_code == 200
    mv = SavingsMovement.objects.get()
    assert mv.quantity == Decimal("100")
    assert mv.ars_amount == Decimal("135000")
    assert mv.location == "Colchón"
    assert mv.from_wallet == wallet
    tx = Transaction.objects.get(category__name="Ahorro")
    assert tx.amount == Decimal("135000.00")
    assert tx.wallet == wallet
    assert mv.linked_expense_id == tx.id


def test_add_movement_buy_without_wallet_creates_no_expense(client_logged, user, usd):
    resp = client_logged.post(
        reverse("savings:add_movement"),
        {
            "asset": usd.id,
            "quantity": "100",
            "ars_amount": "135000",
            "date": "2026-07-05",
            "location": "Ya lo tenía",
        },
    )
    assert resp.status_code == 200
    mv = SavingsMovement.objects.get()
    assert mv.from_wallet is None
    assert mv.linked_expense_id is None
    assert not Transaction.objects.filter(category__name="Ahorro").exists()


def test_delete_movement_also_deletes_linked_ahorro_expense(client_logged, user, wallet, usd):
    mv = _buy(user, usd, "100", "135000", date(2026, 7, 5), wallet=wallet)
    tx = services.create_ahorro_expense(mv)
    resp = client_logged.post(reverse("savings:delete_movement", args=[mv.id]))
    assert resp.status_code == 200
    assert not SavingsMovement.objects.filter(pk=mv.id).exists()
    assert not Transaction.objects.filter(pk=tx.id).exists()


def test_add_movement_rejects_bad_amount(client_logged, user, usd):
    resp = client_logged.post(
        reverse("savings:add_movement"),
        {"asset": usd.id, "quantity": "abc", "ars_amount": "100"},
    )
    assert resp.status_code == 400
    assert SavingsMovement.objects.count() == 0


def test_set_price_creates_snapshot(client_logged, user, usd, usdt):
    resp = client_logged.post(reverse("savings:set_price"), {"price": "1.350"})
    assert resp.status_code == 200
    assert services.current_dollar_price(user) == Decimal("1350.0000")
    # Applied to every USD-quoted asset.
    assert PriceSnapshot.objects.count() == 2


def test_delete_movement_removes_it(client_logged, user, usd):
    mv = _buy(user, usd, "100", "135000", date(2026, 7, 5))
    resp = client_logged.post(reverse("savings:delete_movement", args=[mv.id]))
    assert resp.status_code == 200
    assert SavingsMovement.objects.count() == 0


def test_savings_home_requires_login(client):
    resp = client.get(reverse("savings:home"))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


def test_cannot_delete_other_users_movement(client_logged, django_user_model, usd):
    other = django_user_model.objects.create_user(username="otro", password="x")
    mv = _buy(other, usd, "100", "135000", date(2026, 7, 5))
    resp = client_logged.post(reverse("savings:delete_movement", args=[mv.id]))
    assert resp.status_code == 404
    assert SavingsMovement.objects.filter(pk=mv.id).exists()


# --- Sells --------------------------------------------------------------------


def test_sell_reduces_holding(user, usd):
    _buy(user, usd, "200", "240000", date(2026, 6, 1), location="Colchón")
    _sell(user, usd, "50", "72000", date(2026, 7, 1), location="Colchón")
    portfolio = services.build_portfolio(user)
    row = portfolio["rows"][0]
    assert row["qty"] == Decimal("150")
    assert dict(row["locations"])["Colchón"] == Decimal("150")


def test_fully_sold_asset_is_hidden(user, usd):
    _buy(user, usd, "100", "120000", date(2026, 6, 1))
    _sell(user, usd, "100", "150000", date(2026, 7, 1))
    portfolio = services.build_portfolio(user)
    assert portfolio["rows"] == []
    assert portfolio["total_usd"] == Decimal("0")


def test_saved_ars_reflects_only_sells(user, usd, wallet):
    # Buys are excluded regardless of amount; only the sell credit remains.
    _buy(user, usd, "100", "135000", date(2026, 7, 3), wallet=wallet)
    _sell(user, usd, "40", "60000", date(2026, 7, 20), wallet=wallet)
    assert services.saved_ars(user, "2026-07") == Decimal("-60000.00")


def test_saved_ars_is_a_credit_not_a_discount(user, usd, wallet):
    _sell(user, usd, "50", "80000", date(2026, 7, 5), wallet=wallet)
    assert services.saved_ars(user, "2026-07") == Decimal("-80000.00")


def test_remaining_increases_on_net_rescate(user, usd, wallet):
    budget = MonthlyBudget.objects.create(
        owner=user, period="2026-07", expected_income=Decimal("1800000")
    )
    _buy(user, usd, "500", "600000", date(2026, 5, 1), wallet=wallet)  # earlier stock
    _sell(user, usd, "100", "150000", date(2026, 7, 10), wallet=wallet)
    assert budget.total_saved == Decimal("-150000.00")
    assert budget.remaining == Decimal("1950000.00")


def test_add_movement_sell_creates_sell(client_logged, user, wallet, usd):
    _buy(user, usd, "200", "240000", date(2026, 6, 1), wallet=wallet, location="Colchón")
    resp = client_logged.post(
        reverse("savings:add_movement"),
        {
            "kind": "sell",
            "asset": usd.id,
            "quantity": "50",
            "ars_amount": "75000",
            "date": "2026-07-05",
            "location": "Colchón",
            "from_wallet": wallet.id,
        },
    )
    assert resp.status_code == 200
    mv = SavingsMovement.objects.get(kind=SavingsMovement.Kind.SELL)
    assert mv.quantity == Decimal("50")
    assert mv.ars_amount == Decimal("75000")


def test_sell_rejects_location_without_holdings(client_logged, user, wallet, usd):
    _buy(user, usd, "100", "120000", date(2026, 6, 1), wallet=wallet, location="Colchón")
    resp = client_logged.post(
        reverse("savings:add_movement"),
        {
            "kind": "sell",
            "asset": usd.id,
            "quantity": "10",
            "ars_amount": "15000",
            "location": "Belo",  # no dollars here
            "from_wallet": wallet.id,
        },
    )
    assert resp.status_code == 400
    assert not SavingsMovement.objects.filter(kind=SavingsMovement.Kind.SELL).exists()


def test_sell_rejects_more_than_available(client_logged, user, wallet, usd):
    _buy(user, usd, "100", "120000", date(2026, 6, 1), wallet=wallet, location="Colchón")
    resp = client_logged.post(
        reverse("savings:add_movement"),
        {
            "kind": "sell",
            "asset": usd.id,
            "quantity": "150",  # only 100 available
            "ars_amount": "225000",
            "location": "Colchón",
            "from_wallet": wallet.id,
        },
    )
    assert resp.status_code == 400
    assert not SavingsMovement.objects.filter(kind=SavingsMovement.Kind.SELL).exists()


def test_add_movement_rejects_unknown_kind(client_logged, user, usd):
    resp = client_logged.post(
        reverse("savings:add_movement"),
        {"kind": "convert", "asset": usd.id, "quantity": "10", "ars_amount": "10"},
    )
    assert resp.status_code == 400
    assert SavingsMovement.objects.count() == 0
