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
    data = {"name": "Delivery", "kind": Category.Kind.ANT, "icon": "bike", "parent": ""}
    data.update(over)
    return data


def test_add_category_creates(client_logged, user):
    resp = client_logged.post(reverse("transactions:add_category"), _payload())
    assert resp.status_code == 200
    c = Category.objects.get(owner=user, name="Delivery")
    assert c.kind == Category.Kind.ANT
    assert c.icon == "bike"
    assert c.parent is None


def test_add_category_rejects_empty_name(client_logged):
    resp = client_logged.post(reverse("transactions:add_category"), _payload(name=" "))
    assert resp.status_code == 400
    assert Category.objects.count() == 0


def test_add_category_rejects_duplicate_name_ci(client_logged, user):
    Category.objects.create(owner=user, name="Nafta", kind=Category.Kind.VARIABLE)
    resp = client_logged.post(
        reverse("transactions:add_category"), _payload(name="nafta", kind=Category.Kind.VARIABLE)
    )
    assert resp.status_code == 400
    assert Category.objects.filter(owner=user).count() == 1


def test_add_category_rejects_bad_kind(client_logged):
    resp = client_logged.post(reverse("transactions:add_category"), _payload(kind="nope"))
    assert resp.status_code == 400
    assert Category.objects.count() == 0


def test_unknown_icon_is_dropped(client_logged, user):
    client_logged.post(reverse("transactions:add_category"), _payload(icon="not-an-icon"))
    c = Category.objects.get(owner=user, name="Delivery")
    assert c.icon == ""


def test_add_category_with_parent_group(client_logged, user):
    parent = Category.objects.create(owner=user, name="Gastos Vivienda", kind=Category.Kind.FIXED)
    resp = client_logged.post(
        reverse("transactions:add_category"),
        _payload(name="Alquiler", kind=Category.Kind.FIXED, parent=parent.id),
    )
    assert resp.status_code == 200
    c = Category.objects.get(owner=user, name="Alquiler")
    assert c.parent_id == parent.id


def test_parent_cannot_be_two_levels(client_logged, user):
    grand = Category.objects.create(owner=user, name="Vivienda", kind=Category.Kind.FIXED)
    mid = Category.objects.create(
        owner=user, name="Servicios", kind=Category.Kind.FIXED, parent=grand
    )
    resp = client_logged.post(
        reverse("transactions:add_category"),
        _payload(name="Luz", kind=Category.Kind.FIXED, parent=mid.id),
    )
    assert resp.status_code == 400
    assert not Category.objects.filter(name="Luz").exists()


def test_update_category_changes_fields(client_logged, user):
    c = Category.objects.create(owner=user, name="Cafe", kind=Category.Kind.ANT)
    resp = client_logged.post(
        reverse("transactions:update_category", args=[c.id]),
        _payload(name="Café", kind=Category.Kind.ANT, icon="coffee"),
    )
    assert resp.status_code == 200
    c.refresh_from_db()
    assert c.name == "Café"
    assert c.icon == "coffee"


def test_update_cannot_be_its_own_parent(client_logged, user):
    c = Category.objects.create(owner=user, name="Ocio", kind=Category.Kind.VARIABLE)
    resp = client_logged.post(
        reverse("transactions:update_category", args=[c.id]),
        _payload(name="Ocio", kind=Category.Kind.VARIABLE, parent=c.id),
    )
    assert resp.status_code == 400


def test_group_cannot_be_nested(client_logged, user):
    group = Category.objects.create(owner=user, name="Vivienda", kind=Category.Kind.FIXED)
    Category.objects.create(owner=user, name="Luz", kind=Category.Kind.FIXED, parent=group)
    other = Category.objects.create(owner=user, name="Otros", kind=Category.Kind.FIXED)
    resp = client_logged.post(
        reverse("transactions:update_category", args=[group.id]),
        _payload(name="Vivienda", kind=Category.Kind.FIXED, parent=other.id),
    )
    assert resp.status_code == 400


def test_delete_category_sets_transactions_null(client_logged, user, wallet):
    c = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    tx = Transaction.objects.create(
        owner=user, wallet=wallet, category=c, amount=Decimal("1000"),
        kind=Transaction.Kind.EXPENSE, date=date(2026, 6, 1),
    )
    resp = client_logged.post(reverse("transactions:delete_category", args=[c.id]))
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.category_id is None


def test_delete_category_blocked_when_used_by_recurring(client_logged, user, wallet):
    c = Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED)
    RecurringExpense.objects.create(
        owner=user, name="Alquiler", default_amount=Decimal("1"), category=c, wallet=wallet,
    )
    resp = client_logged.post(reverse("transactions:delete_category", args=[c.id]))
    assert resp.status_code == 400
    assert Category.objects.filter(pk=c.id).exists()


def test_categories_page_renders(client_logged, user):
    Category.objects.create(owner=user, name="Delivery", kind=Category.Kind.ANT, icon="bike")
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
    c = Category.objects.create(owner=other, name="Ajena", kind=Category.Kind.ANT)
    resp = client_logged.post(reverse("transactions:delete_category", args=[c.id]))
    assert resp.status_code == 404
    assert Category.objects.filter(pk=c.id).exists()
