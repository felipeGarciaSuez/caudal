from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budgets.models import MonthlyBudget
from apps.transactions.models import Category, Transaction
from apps.wallets.models import CardStatement, Wallet

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
def category(user):
    return Category.objects.create(owner=user, name="Café", kind=Category.Kind.ANT)


def test_home_redirects_to_current_month(client_logged):
    resp = client_logged.get(reverse("dashboard:home"))
    assert resp.status_code == 302
    assert "/m/" in resp["Location"]


def test_month_view_requires_login(client):
    resp = client.get(reverse("dashboard:month", args=["2026-06"]))
    assert resp.status_code == 302  # redirect to login
    assert "/accounts/login/" in resp["Location"]


def test_login_page_renders_branded(client):
    resp = client.get(reverse("login"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Caudal" in body
    assert "Ingresar" in body
    # The Django admin login chrome must not be here.
    assert "Django administration" not in body


def test_login_authenticates_and_redirects(client, django_user_model):
    django_user_model.objects.create_user(username="felipe", password="caudal123")
    resp = client.post(reverse("login"), {"username": "felipe", "password": "caudal123"})
    assert resp.status_code == 302
    assert resp["Location"] == "/"


def test_logout_redirects_to_login(client_logged):
    resp = client_logged.post(reverse("logout"))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


def test_month_view_renders_full_page(client_logged, user, wallet, category):
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=category,
        amount=Decimal("3500.00"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-05",
    )
    resp = client_logged.get(reverse("dashboard:month", args=["2026-06"]))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Junio 2026" in body
    assert "Resto sueldo" in body
    assert "Café" in body
    assert "3.500,00" in body


def test_category_detail_lists_movements(client_logged, user, wallet, category):
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=category,
        amount=Decimal("3500.00"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-05",
        description="Cafecito",
    )
    resp = client_logged.get(reverse("dashboard:category_detail", args=["2026-06", category.id]))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Cafecito" in body
    assert "ICBC" in body  # the wallet / DONDE


def test_add_transaction_creates_expense_and_updates_resto(client_logged, user, wallet, category):
    MonthlyBudget.objects.create(
        owner=user, period="2026-06", expected_income=Decimal("1000000.00")
    )
    resp = client_logged.post(
        reverse("dashboard:add_transaction"),
        {
            "period": "2026-06",
            "kind": "expense",
            "date": "2026-06-15",
            "is_paid": "on",
            "amount": "12500.50",
            "wallet": wallet.id,
            "category": category.id,
        },
    )
    assert resp.status_code == 200
    tx = Transaction.objects.get()
    assert tx.owner == user
    assert tx.amount == Decimal("12500.50")
    assert tx.period == "2026-06"
    # RESTO SUELDO reflected in the returned body.
    assert b"987.499,50" in resp.content


def test_add_transaction_without_category_keeps_description(client_logged, user, wallet):
    # "Sin categoría" submits an empty category; the description is what
    # identifies the loose/ant expense afterwards.
    resp = client_logged.post(
        reverse("dashboard:add_transaction"),
        {
            "period": "2026-06",
            "kind": "expense",
            "date": "2026-06-15",
            "is_paid": "on",
            "amount": "800.00",
            "wallet": wallet.id,
            "category": "",
            "description": "Cafe con Juan",
        },
    )
    assert resp.status_code == 200
    tx = Transaction.objects.get()
    assert tx.category is None
    assert tx.description == "Cafe con Juan"


def test_add_transaction_invalid_returns_400(client_logged, user, wallet):
    resp = client_logged.post(
        reverse("dashboard:add_transaction"),
        {"period": "2026-06", "kind": "expense", "date": "2026-06-15", "wallet": wallet.id},
    )
    assert resp.status_code == 400
    assert Transaction.objects.count() == 0


def test_toggle_paid_flips_flag(client_logged, user, wallet, category):
    tx = Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=category,
        amount=Decimal("1000"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-10",
        is_paid=True,
    )
    resp = client_logged.post(reverse("dashboard:toggle_paid", args=[tx.id]))
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.is_paid is False


def test_set_income_creates_budget(client_logged, user):
    resp = client_logged.post(
        reverse("dashboard:set_income", args=["2026-06"]),
        {"expected_income": "1850000"},
    )
    assert resp.status_code == 200
    budget = MonthlyBudget.objects.get(owner=user, period="2026-06")
    assert budget.expected_income == Decimal("1850000")


def test_toggle_paid_scope_month_returns_body_with_summary(client_logged, user, wallet):
    fixed = Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED)
    tx = Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=fixed,
        amount=Decimal("480000"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-03",
        is_paid=False,
    )
    resp = client_logged.post(reverse("dashboard:toggle_paid", args=[tx.id]), {"scope": "month"})
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.is_paid is True
    body = resp.content.decode()
    assert "Gastos grandes" in body  # full month body, not just the row
    assert "1/1 pagados" in body


def test_update_amount_changes_fixed_expense(client_logged, user, wallet):
    fixed = Category.objects.create(owner=user, name="Luz", kind=Category.Kind.FIXED)
    tx = Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=fixed,
        amount=Decimal("40000"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-12",
        is_paid=False,
    )
    resp = client_logged.post(
        reverse("dashboard:update_amount", args=[tx.id]), {"amount": "52350.75"}
    )
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.amount == Decimal("52350.75")


def test_update_amount_rejects_invalid(client_logged, user, wallet):
    fixed = Category.objects.create(owner=user, name="Gas", kind=Category.Kind.FIXED)
    tx = Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=fixed,
        amount=Decimal("20000"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-12",
    )
    resp = client_logged.post(reverse("dashboard:update_amount", args=[tx.id]), {"amount": "abc"})
    assert resp.status_code == 400
    tx.refresh_from_db()
    assert tx.amount == Decimal("20000")


def test_cannot_toggle_other_users_transaction(client_logged, django_user_model, wallet):
    other = django_user_model.objects.create_user(username="otro", password="x")
    other_wallet = Wallet.objects.create(owner=other, name="X", kind=Wallet.Kind.CASH)
    tx = Transaction.objects.create(
        owner=other,
        wallet=other_wallet,
        amount=Decimal("500"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-10",
    )
    resp = client_logged.post(reverse("dashboard:toggle_paid", args=[tx.id]))
    assert resp.status_code == 404


def test_imported_fixed_expense_is_aggregated_not_checklist(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    subs = Category.objects.create(owner=user, name="Suscripciones", kind=Category.Kind.FIXED)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=subs,
        amount=Decimal("5000"),
        kind=Transaction.Kind.EXPENSE,
        date=timezone.localdate(),
        source=Transaction.Source.IMPORT,
    )
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    assert resp.context["fixed_rows"] == []
    assert resp.context["m"]["fixed_count"] == 0
    big_names = {r["category__name"] for r in resp.context["big_rows"]}
    assert "Suscripciones" in big_names
    # Still counted toward the month total, just not as a checklist row.
    assert resp.context["m"]["big_total"] == Decimal("5000.00")


def test_manual_fixed_expense_is_checklist_row(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    fixed = Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=fixed,
        amount=Decimal("100000"),
        kind=Transaction.Kind.EXPENSE,
        date=timezone.localdate(),
    )
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    assert len(resp.context["fixed_rows"]) == 1
    assert resp.context["fixed_rows"][0].category == fixed


def test_variable_big_expense_shows_in_grandes_not_hormiga(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    super_cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=super_cat,
        amount=Decimal("50000"),
        kind=Transaction.Kind.EXPENSE,
        date=timezone.localdate(),
    )
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    big_names = {r["category__name"] for r in resp.context["big_rows"]}
    ant_names = {r["category__name"] for r in resp.context["ant_rows"]}
    assert "Super" in big_names
    assert "Super" not in ant_names


def test_categorizacion_section_removed(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    body = resp.content.decode()
    assert "Categorización" not in body
    assert "combined_rows" not in resp.context


def test_checklist_groups_vivienda_together(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    vivienda = Category.objects.create(owner=user, name="Gastos Vivienda", kind=Category.Kind.FIXED)
    alquiler = Category.objects.create(
        owner=user, name="Alquiler", kind=Category.Kind.FIXED, parent=vivienda
    )
    agua = Category.objects.create(
        owner=user, name="Agua", kind=Category.Kind.FIXED, parent=vivienda
    )
    telefono = Category.objects.create(owner=user, name="Teléfono", kind=Category.Kind.FIXED)
    today = timezone.localdate()
    for cat, amount in [(alquiler, "100000"), (agua, "5000"), (telefono, "10000")]:
        Transaction.objects.create(
            owner=user,
            wallet=wallet,
            category=cat,
            amount=Decimal(amount),
            kind=Transaction.Kind.EXPENSE,
            date=today,
        )
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    groups = resp.context["fixed_groups"]
    assert len(groups) == 2
    names_by_group = [{tx.category.name for tx in g["rows"]} for g in groups]
    assert {"Alquiler", "Agua"} in names_by_group
    assert {"Teléfono"} in names_by_group
    body = resp.content.decode()
    assert "Gastos Vivienda" in body
    assert "Otros" in body


def test_checklist_single_group_shows_no_label(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    fixed = Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=fixed,
        amount=Decimal("100000"),
        kind=Transaction.Kind.EXPENSE,
        date=timezone.localdate(),
    )
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    assert len(resp.context["fixed_groups"]) == 1
    assert "fx-group-label" not in resp.content.decode()


def test_group_category_excluded_from_selectors(client_logged, user):
    period = timezone.localdate().strftime("%Y-%m")
    vivienda = Category.objects.create(owner=user, name="Gastos Vivienda", kind=Category.Kind.FIXED)
    Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED, parent=vivienda)
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    quick_names = {c.name for c in resp.context["quick_categories"]}
    big_names = {c.name for c in resp.context["big_categories"]}
    assert "Gastos Vivienda" not in quick_names
    assert "Gastos Vivienda" not in big_names
    assert "Alquiler" in quick_names


def test_total_spent_unaffected_by_regrouping(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    fixed_cat = Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED)
    subs_cat = Category.objects.create(owner=user, name="Suscripciones", kind=Category.Kind.FIXED)
    super_cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    ant_cat = Category.objects.create(owner=user, name="Café", kind=Category.Kind.ANT)
    today = timezone.localdate()
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=fixed_cat,
        amount=Decimal("100000"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
    )  # checklist (manual, fixed)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=subs_cat,
        amount=Decimal("5000"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
        source=Transaction.Source.IMPORT,
    )  # aggregated (imported, fixed)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=super_cat,
        amount=Decimal("20000"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
    )  # aggregated (variable)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=ant_cat,
        amount=Decimal("3000"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
    )  # hormiga
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    m = resp.context["m"]
    assert m["fixed_total"] == Decimal("100000.00")
    assert m["big_total"] == Decimal("25000.00")
    assert m["ant"] == Decimal("3000.00")
    assert m["total_spent"] == Decimal("128000.00")


def test_big_categories_exclude_ant(client_logged, user):
    period = timezone.localdate().strftime("%Y-%m")
    Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED)
    Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    Category.objects.create(owner=user, name="Café", kind=Category.Kind.ANT)
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    names = {c.name for c in resp.context["big_categories"]}
    assert names == {"Alquiler", "Super"}


def test_hormiga_panel_ranks_ant_categories(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    today = timezone.localdate()
    cafe = Category.objects.create(owner=user, name="Café", kind=Category.Kind.ANT)
    deli = Category.objects.create(owner=user, name="Delivery", kind=Category.Kind.ANT)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=cafe,
        amount=Decimal("3000"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
    )
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=deli,
        amount=Decimal("12000"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
    )
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    body = resp.content.decode()
    assert "Gastos hormiga" in body
    assert "Delivery" in body
    assert "Café" in body


def test_hormiga_rows_carry_individual_movements(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    today = timezone.localdate()
    cafe = Category.objects.create(owner=user, name="Café", kind=Category.Kind.ANT)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=cafe,
        amount=Decimal("3000"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
        description="Cafecito de la mañana",
    )
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=cafe,
        amount=Decimal("2500"),
        kind=Transaction.Kind.EXPENSE,
        date=today,
        description="Cafecito de la tarde",
    )
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    ant_rows = resp.context["ant_rows"]
    assert len(ant_rows) == 1
    assert len(ant_rows[0]["movements"]) == 2
    body = resp.content.decode()
    assert "Cafecito de la mañana" in body
    assert "Cafecito de la tarde" in body
    assert "rank-detail" in body


# --- editar / eliminar movimientos y single-vs-agrupado en gastos grandes ---


def _variable_expense(user, wallet, cat, amount, date, **kw):
    return Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=cat,
        amount=Decimal(amount),
        kind=Transaction.Kind.EXPENSE,
        date=date,
        **kw,
    )


def test_delete_transaction_removes_and_rerenders_month(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    tx = _variable_expense(user, wallet, cat, "12000", timezone.localdate())
    resp = client_logged.post(
        reverse("dashboard:delete_transaction", args=[tx.id]),
        {"scope": "month", "period": period},
    )
    assert resp.status_code == 200
    assert not Transaction.objects.filter(pk=tx.id).exists()
    assert "Gastos grandes" in resp.content.decode()  # full month body back


def test_cannot_delete_other_users_transaction(client_logged, django_user_model):
    other = django_user_model.objects.create_user(username="otro", password="x")
    ow = Wallet.objects.create(owner=other, name="X", kind=Wallet.Kind.CASH)
    tx = Transaction.objects.create(
        owner=other,
        wallet=ow,
        amount=Decimal("500"),
        kind=Transaction.Kind.EXPENSE,
        date="2026-06-10",
    )
    resp = client_logged.post(reverse("dashboard:delete_transaction", args=[tx.id]))
    assert resp.status_code == 404
    assert Transaction.objects.filter(pk=tx.id).exists()


def test_edit_transaction_updates_fields(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    other = Category.objects.create(owner=user, name="Ocio", kind=Category.Kind.VARIABLE)
    tx = _variable_expense(user, wallet, cat, "12000", timezone.localdate())
    resp = client_logged.post(
        reverse("dashboard:edit_transaction", args=[tx.id]),
        {
            "scope": "month",
            "period": period,
            "kind": "expense",
            "date": "2026-06-15",
            "amount": "18500",
            "wallet": wallet.id,
            "category": other.id,
            "description": "Compra grande",
            "is_paid": "on",
        },
    )
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.amount == Decimal("18500")
    assert tx.category == other
    assert tx.description == "Compra grande"


def test_edit_transaction_invalid_returns_400(client_logged, user, wallet):
    cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    tx = _variable_expense(user, wallet, cat, "12000", timezone.localdate())
    resp = client_logged.post(
        reverse("dashboard:edit_transaction", args=[tx.id]),
        {
            "scope": "month",
            "kind": "expense",
            "amount": "abc",
            "wallet": wallet.id,
            "date": "2026-06-15",
        },
    )
    assert resp.status_code == 400
    tx.refresh_from_db()
    assert tx.amount == Decimal("12000")


def test_big_row_single_movement_is_editable(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    cat = Category.objects.create(owner=user, name="Seguro", kind=Category.Kind.VARIABLE)
    tx = _variable_expense(user, wallet, cat, "25000", timezone.localdate())
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    rows = {r["category__name"]: r for r in resp.context["big_rows"]}
    assert rows["Seguro"]["single"] == tx  # one movement -> surfaced as itself
    # The delete control for that tx is present in the main view.
    assert reverse("dashboard:delete_transaction", args=[tx.id]) in resp.content.decode()


def test_big_row_aggregates_when_multiple(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    _variable_expense(user, wallet, cat, "12000", timezone.localdate())
    _variable_expense(user, wallet, cat, "8000", timezone.localdate())
    resp = client_logged.get(reverse("dashboard:month", args=[period]))
    rows = {r["category__name"]: r for r in resp.context["big_rows"]}
    assert rows["Super"]["single"] is None  # several movements -> grouped
    assert rows["Super"]["count"] == 2
    assert rows["Super"]["total"] == Decimal("20000.00")


def test_delete_from_detail_rerenders_detail_body(client_logged, user, wallet):
    period = timezone.localdate().strftime("%Y-%m")
    cat = Category.objects.create(owner=user, name="Super", kind=Category.Kind.VARIABLE)
    tx = _variable_expense(user, wallet, cat, "12000", timezone.localdate())
    resp = client_logged.post(
        reverse("dashboard:delete_transaction", args=[tx.id]),
        {"scope": "detail", "period": period, "category_id": cat.id},
    )
    assert resp.status_code == 200
    assert not Transaction.objects.filter(pk=tx.id).exists()
    assert "Total Super" in resp.content.decode()  # detail body re-rendered


def test_settings_hub_renders(client_logged):
    resp = client_logged.get(reverse("dashboard:settings"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Ajustes" in body
    assert reverse("imports:rules") in body
    assert reverse("wallets:wallets") in body


# --- Resumen de tarjeta (gasto grande desglosable) -------------------------


def _card(user, name="ICBC Visa"):
    return Wallet.objects.create(owner=user, name=name, kind=Wallet.Kind.CREDIT_CARD)


def _card_charge(user, card, amount, period="2026-06", **kw):
    return Transaction.objects.create(
        owner=user,
        wallet=card,
        amount=Decimal(amount),
        kind=Transaction.Kind.EXPENSE,
        date=f"{period}-10",
        needs_review=kw.pop("needs_review", True),
        **kw,
    )


def test_card_charges_grouped_into_statement_not_big_rows(client_logged, user):
    card = _card(user)
    _card_charge(user, card, "12000")
    _card_charge(user, card, "8000")
    resp = client_logged.get(reverse("dashboard:month", args=["2026-06"]))
    statements = resp.context["statement_rows"]
    assert len(statements) == 1
    assert statements[0]["wallet"] == card
    assert statements[0]["count"] == 2
    assert statements[0]["total"] == Decimal("20000.00")
    # Card charges must not leak into the per-category big rows.
    assert resp.context["big_rows"] == []
    assert resp.context["m"]["statements_total"] == Decimal("20000.00")


def test_statement_counts_in_resto_even_if_unpaid(client_logged, user):
    MonthlyBudget.objects.create(owner=user, period="2026-06", expected_income=Decimal("100000"))
    card = _card(user)
    _card_charge(user, card, "30000")
    resp = client_logged.get(reverse("dashboard:month", args=["2026-06"]))
    m = resp.context["m"]
    assert m["total_spent"] == Decimal("30000.00")
    assert m["remaining"] == Decimal("70000.00")  # counts although statement unpaid


def test_toggle_statement_paid_persists(client_logged, user):
    card = _card(user)
    _card_charge(user, card, "5000")
    resp = client_logged.post(
        reverse("dashboard:toggle_statement_paid", args=[card.id, "2026-06"]),
        {"scope": "month"},
    )
    assert resp.status_code == 200
    st = CardStatement.objects.get(owner=user, wallet=card, period="2026-06")
    assert st.is_paid is True
    # toggling again flips back
    client_logged.post(reverse("dashboard:toggle_statement_paid", args=[card.id, "2026-06"]))
    st.refresh_from_db()
    assert st.is_paid is False


def test_statement_charge_update_sets_category_and_share(client_logged, user):
    card = _card(user)
    tx = _card_charge(user, card, "10000")
    cat = Category.objects.create(owner=user, name="Súper", kind=Category.Kind.VARIABLE)
    resp = client_logged.post(
        reverse("dashboard:statement_charge_update", args=[tx.id]),
        {"category": cat.id, "share": "0.500"},
    )
    assert resp.status_code == 200
    tx.refresh_from_db()
    assert tx.category == cat
    assert tx.shared_ratio == Decimal("0.500")
    assert tx.is_shared is True
    assert tx.needs_review is False
    assert tx.own_amount == Decimal("5000.00")


def test_statement_charge_delete(client_logged, user):
    card = _card(user)
    tx = _card_charge(user, card, "10000")
    resp = client_logged.post(reverse("dashboard:statement_charge_delete", args=[tx.id]))
    assert resp.status_code == 200
    assert not Transaction.objects.filter(pk=tx.id).exists()


def test_statement_detail_renders_and_lists_charges(client_logged, user):
    card = _card(user)
    _card_charge(user, card, "10000", description="ANTHROPIC")
    resp = client_logged.get(reverse("dashboard:card_statement", args=[card.id, "2026-06"]))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ICBC Visa" in body
    assert "ANTHROPIC" in body


def test_cannot_touch_other_users_statement_charge(client_logged, django_user_model):
    other = django_user_model.objects.create_user(username="otro", password="x")
    ocard = _card(other)
    tx = _card_charge(other, ocard, "500")
    resp = client_logged.post(reverse("dashboard:statement_charge_delete", args=[tx.id]))
    assert resp.status_code == 404
    assert Transaction.objects.filter(pk=tx.id).exists()
