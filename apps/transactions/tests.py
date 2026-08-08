from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budgets.models import RecurringExpense
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


def _payload(**over):
    data = {"name": "Delivery", "icon": "bike"}
    data.update(over)
    return data


def test_add_category_creates(client_logged, user):
    resp = client_logged.post(reverse("transactions:add_category"), _payload())
    assert resp.status_code == 200
    c = Category.objects.get(owner=user, name="Delivery")
    assert c.icon == "bike"


def test_add_category_rejects_empty_name(client_logged):
    resp = client_logged.post(reverse("transactions:add_category"), _payload(name=" "))
    assert resp.status_code == 400
    assert Category.objects.count() == 0


def test_add_category_rejects_duplicate_name_ci(client_logged, user):
    Category.objects.create(owner=user, name="Nafta")
    resp = client_logged.post(reverse("transactions:add_category"), _payload(name="nafta"))
    assert resp.status_code == 400
    assert Category.objects.filter(owner=user).count() == 1


def test_unknown_icon_is_dropped(client_logged, user):
    client_logged.post(reverse("transactions:add_category"), _payload(icon="not-an-icon"))
    c = Category.objects.get(owner=user, name="Delivery")
    assert c.icon == ""


def test_update_category_changes_fields(client_logged, user):
    c = Category.objects.create(owner=user, name="Cafe")
    resp = client_logged.post(
        reverse("transactions:update_category", args=[c.id]),
        _payload(name="Café", icon="coffee"),
    )
    assert resp.status_code == 200
    c.refresh_from_db()
    assert c.name == "Café"
    assert c.icon == "coffee"


def test_delete_category_sets_transactions_null(client_logged, user, wallet):
    c = Category.objects.create(owner=user, name="Super")
    tx = Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=c,
        amount=Decimal("1000"),
        kind=Transaction.Kind.EXPENSE,
        date=date(2026, 6, 1),
    )
    resp = client_logged.post(reverse("transactions:delete_category", args=[c.id]))
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.category_id is None


def test_delete_category_blocked_when_used_by_recurring(client_logged, user, wallet):
    c = Category.objects.create(owner=user, name="Alquiler")
    RecurringExpense.objects.create(
        owner=user,
        name="Alquiler",
        default_amount=Decimal("1"),
        category=c,
        wallet=wallet,
    )
    resp = client_logged.post(reverse("transactions:delete_category", args=[c.id]))
    assert resp.status_code == 400
    assert Category.objects.filter(pk=c.id).exists()


def test_categories_page_renders(client_logged, user):
    Category.objects.create(owner=user, name="Delivery", icon="bike")
    resp = client_logged.get(reverse("transactions:categories"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Categorías" in body
    assert "Delivery" in body


def test_category_views_require_login(client):
    resp = client.post(reverse("transactions:add_category"), _payload())
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


def test_user_cannot_touch_another_users_category(client_logged, django_user_model):
    other = django_user_model.objects.create_user(username="otro", password="x")
    c = Category.objects.create(owner=other, name="Ajena")
    resp = client_logged.post(reverse("transactions:delete_category", args=[c.id]))
    assert resp.status_code == 404
    assert Category.objects.filter(pk=c.id).exists()
