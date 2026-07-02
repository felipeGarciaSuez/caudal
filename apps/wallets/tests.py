from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

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


def _payload(**over):
    data = {"name": "ICBC", "kind": Wallet.Kind.BANK, "currency": "ARS"}
    data.update(over)
    return data


def test_add_wallet_creates(client_logged, user):
    resp = client_logged.post(reverse("wallets:add_wallet"), _payload())
    assert resp.status_code == 200
    w = Wallet.objects.get(owner=user, name="ICBC")
    assert w.kind == Wallet.Kind.BANK
    assert w.is_active is True
    assert w.currency == "ARS"


def test_add_wallet_credit_card_keeps_days(client_logged, user):
    resp = client_logged.post(
        reverse("wallets:add_wallet"),
        _payload(name="ICBC Visa", kind=Wallet.Kind.CREDIT_CARD, closing_day="20", due_day="10"),
    )
    assert resp.status_code == 200
    w = Wallet.objects.get(owner=user, name="ICBC Visa")
    assert w.closing_day == 20
    assert w.due_day == 10


def test_non_credit_card_ignores_days(client_logged, user):
    client_logged.post(
        reverse("wallets:add_wallet"),
        _payload(name="Efectivo", kind=Wallet.Kind.CASH, closing_day="20", due_day="10"),
    )
    w = Wallet.objects.get(owner=user, name="Efectivo")
    assert w.closing_day is None
    assert w.due_day is None


def test_add_wallet_rejects_empty_name(client_logged):
    resp = client_logged.post(reverse("wallets:add_wallet"), _payload(name="  "))
    assert resp.status_code == 400
    assert Wallet.objects.count() == 0


def test_add_wallet_rejects_duplicate_name_case_insensitive(client_logged, user):
    Wallet.objects.create(owner=user, name="MP", kind=Wallet.Kind.WALLET)
    resp = client_logged.post(
        reverse("wallets:add_wallet"), _payload(name="mp", kind=Wallet.Kind.WALLET)
    )
    assert resp.status_code == 400
    assert Wallet.objects.filter(owner=user).count() == 1


def test_add_wallet_rejects_bad_kind(client_logged):
    resp = client_logged.post(reverse("wallets:add_wallet"), _payload(kind="nope"))
    assert resp.status_code == 400
    assert Wallet.objects.count() == 0


def test_update_wallet_changes_fields(client_logged, user):
    w = Wallet.objects.create(owner=user, name="Uala", kind=Wallet.Kind.WALLET)
    resp = client_logged.post(
        reverse("wallets:update_wallet", args=[w.id]),
        _payload(name="Ualá", kind=Wallet.Kind.WALLET, currency="usd"),
    )
    assert resp.status_code == 200
    w.refresh_from_db()
    assert w.name == "Ualá"
    assert w.currency == "USD"


def test_update_wallet_allows_keeping_own_name(client_logged, user):
    w = Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK)
    resp = client_logged.post(
        reverse("wallets:update_wallet", args=[w.id]),
        _payload(name="ICBC", kind=Wallet.Kind.BANK),
    )
    assert resp.status_code == 200


def test_toggle_wallet_flips_active(client_logged, user):
    w = Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK, is_active=True)
    client_logged.post(reverse("wallets:toggle_wallet", args=[w.id]))
    w.refresh_from_db()
    assert w.is_active is False


def test_delete_wallet_without_movements(client_logged, user):
    w = Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK)
    resp = client_logged.post(reverse("wallets:delete_wallet", args=[w.id]))
    assert resp.status_code == 200
    assert not Wallet.objects.filter(pk=w.id).exists()


def test_delete_wallet_with_movements_is_blocked(client_logged, user):
    w = Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK)
    cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    Transaction.objects.create(
        owner=user, wallet=w, category=cat, amount=Decimal("1000"),
        kind=Transaction.Kind.EXPENSE, date=date(2026, 6, 1),
    )
    resp = client_logged.post(reverse("wallets:delete_wallet", args=[w.id]))
    assert resp.status_code == 400
    # Blocked: the wallet (and its history) must survive.
    assert Wallet.objects.filter(pk=w.id).exists()


def test_wallets_page_renders(client_logged, user):
    Wallet.objects.create(owner=user, name="Mercado Pago", kind=Wallet.Kind.WALLET)
    resp = client_logged.get(reverse("wallets:wallets"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Billeteras" in body
    assert "Mercado Pago" in body


def test_wallet_views_require_login(client):
    resp = client.post(reverse("wallets:add_wallet"), _payload())
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


def test_user_cannot_touch_another_users_wallet(client_logged, django_user_model):
    other = django_user_model.objects.create_user(username="otro", password="x")
    w = Wallet.objects.create(owner=other, name="Ajena", kind=Wallet.Kind.BANK)
    resp = client_logged.post(reverse("wallets:delete_wallet", args=[w.id]))
    assert resp.status_code == 404
    assert Wallet.objects.filter(pk=w.id).exists()
