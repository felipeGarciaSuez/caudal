from datetime import date
from decimal import Decimal

import pytest

from apps.budgets.models import MonthlyBudget, RecurringExpense
from apps.budgets.services import ensure_month_fixed
from apps.transactions.models import Category, Transaction
from apps.wallets.models import Wallet

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="tester", password="x")


@pytest.fixture
def wallet(user):
    return Wallet.objects.create(owner=user, name="ICBC", kind=Wallet.Kind.BANK)


def _cat(user, name, kind):
    return Category.objects.create(owner=user, name=name, kind=kind)


def _expense(user, wallet, category, amount, when):
    return Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=category,
        amount=Decimal(amount),
        kind=Transaction.Kind.EXPENSE,
        date=when,
    )


def test_ensure_month_fixed_generates_pending_and_is_idempotent(user, wallet):
    cat = _cat(user, "Alquiler", Category.Kind.FIXED)
    template = RecurringExpense.objects.create(
        owner=user,
        name="Alquiler",
        default_amount=Decimal("480000"),
        category=cat,
        wallet=wallet,
        day_of_month=3,
    )

    created = ensure_month_fixed(user, "2026-07")
    assert created == 1
    tx = Transaction.objects.get(recurring_expense=template, period="2026-07")
    assert tx.is_paid is False
    assert tx.amount == Decimal("480000")
    assert tx.category == cat
    assert tx.date == date(2026, 7, 3)

    # Re-running never duplicates.
    assert ensure_month_fixed(user, "2026-07") == 0
    assert Transaction.objects.filter(recurring_expense=template, period="2026-07").count() == 1


def test_ensure_month_fixed_clamps_day_to_month_length(user, wallet):
    cat = _cat(user, "Teléfono", Category.Kind.FIXED)
    RecurringExpense.objects.create(
        owner=user,
        name="Teléfono",
        default_amount=Decimal("25000"),
        category=cat,
        wallet=wallet,
        day_of_month=31,
    )
    ensure_month_fixed(user, "2026-02")  # February has 28 days
    tx = Transaction.objects.get(period="2026-02")
    assert tx.date == date(2026, 2, 28)


def test_ensure_month_fixed_skips_inactive_templates(user, wallet):
    cat = _cat(user, "Gym", Category.Kind.FIXED)
    RecurringExpense.objects.create(
        owner=user,
        name="Gym",
        default_amount=Decimal("22000"),
        category=cat,
        wallet=wallet,
        is_active=False,
    )
    assert ensure_month_fixed(user, "2026-07") == 0
    assert Transaction.objects.count() == 0


def test_period_is_derived_from_date(user, wallet):
    cat = _cat(user, "Super", Category.Kind.VARIABLE)
    tx = _expense(user, wallet, cat, "1000.00", date(2026, 6, 15))
    assert tx.period == "2026-06"


def test_remaining_and_breakdown(user, wallet):
    fixed = _cat(user, "Alquiler", Category.Kind.FIXED)
    variable = _cat(user, "Super", Category.Kind.VARIABLE)
    ant = _cat(user, "Café", Category.Kind.ANT)

    _expense(user, wallet, fixed, "500000.00", date(2026, 6, 1))
    _expense(user, wallet, variable, "120000.00", date(2026, 6, 10))
    _expense(user, wallet, ant, "8000.00", date(2026, 6, 12))
    # Different month — must not leak into June totals.
    _expense(user, wallet, ant, "9999.00", date(2026, 7, 3))

    budget = MonthlyBudget.objects.create(
        owner=user, period="2026-06", expected_income=Decimal("1800000.00")
    )

    assert budget.total_fixed == Decimal("500000.00")
    assert budget.total_variable == Decimal("120000.00")
    assert budget.total_ant == Decimal("8000.00")
    assert budget.total_spent == Decimal("628000.00")
    assert budget.remaining == Decimal("1172000.00")


def test_remaining_with_no_expenses_equals_income(user):
    budget = MonthlyBudget.objects.create(
        owner=user, period="2026-05", expected_income=Decimal("1730000.00")
    )
    assert budget.total_spent == Decimal("0.00")
    assert budget.remaining == Decimal("1730000.00")


def test_needs_review_expenses_do_not_count(user, wallet):
    cat = _cat(user, "Super", Category.Kind.VARIABLE)
    _expense(user, wallet, cat, "50000.00", date(2026, 6, 5))
    # A card item pending review must not count until confirmed.
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=cat,
        amount=Decimal("30000.00"),
        kind=Transaction.Kind.EXPENSE,
        date=date(2026, 6, 6),
        needs_review=True,
    )
    budget = MonthlyBudget.objects.create(
        owner=user, period="2026-06", expected_income=Decimal("1000000.00")
    )
    assert budget.total_spent == Decimal("50000.00")


def test_shared_expense_counts_only_own_part(user, wallet):
    cat = _cat(user, "Alquiler", Category.Kind.FIXED)
    Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=cat,
        amount=Decimal("100000.00"),
        kind=Transaction.Kind.EXPENSE,
        date=date(2026, 6, 1),
        is_shared=True,
        shared_ratio=Decimal("0.500"),
    )
    budget = MonthlyBudget.objects.create(
        owner=user, period="2026-06", expected_income=Decimal("1000000.00")
    )
    assert budget.total_spent == Decimal("50000.00")  # only my half
    assert budget.remaining == Decimal("950000.00")


def test_own_amount_applies_shared_ratio(user, wallet):
    cat = _cat(user, "Expensas", Category.Kind.FIXED)
    tx = Transaction.objects.create(
        owner=user,
        wallet=wallet,
        category=cat,
        amount=Decimal("100000.00"),
        kind=Transaction.Kind.EXPENSE,
        date=date(2026, 6, 1),
        is_shared=True,
        shared_ratio=Decimal("0.500"),
    )
    assert tx.own_amount == Decimal("50000.00")


def test_own_amount_full_when_not_shared(user, wallet):
    cat = _cat(user, "Nafta", Category.Kind.VARIABLE)
    tx = _expense(user, wallet, cat, "45000.00", date(2026, 6, 1))
    assert tx.own_amount == Decimal("45000.00")


# --- Recurring expense management views ------------------------------------


@pytest.fixture
def client_logged(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def fixed_cat(user):
    return Category.objects.create(owner=user, name="Alquiler", kind=Category.Kind.FIXED)


def _payload(cat, wallet, **over):
    data = {
        "name": "Alquiler",
        "default_amount": "350000.00",
        "day_of_month": "10",
        "category": cat.id,
        "wallet": wallet.id,
    }
    data.update(over)
    return data


def test_add_recurring_creates_template(client_logged, user, wallet, fixed_cat):
    from django.urls import reverse

    resp = client_logged.post(reverse("budgets:add_recurring"), _payload(fixed_cat, wallet))
    assert resp.status_code == 200
    r = RecurringExpense.objects.get(owner=user, name="Alquiler")
    assert r.default_amount == Decimal("350000.00")
    assert r.day_of_month == 10
    assert r.is_active is True


def test_add_recurring_seeds_current_month(client_logged, user, wallet, fixed_cat):
    from django.urls import reverse
    from django.utils import timezone

    client_logged.post(reverse("budgets:add_recurring"), _payload(fixed_cat, wallet))
    period = timezone.localdate().strftime("%Y-%m")
    tx = Transaction.objects.get(owner=user, recurring_expense__isnull=False)
    assert tx.period == period
    assert tx.is_paid is False
    assert tx.source == Transaction.Source.MANUAL


def test_add_recurring_rejects_bad_amount(client_logged, wallet, fixed_cat):
    from django.urls import reverse

    resp = client_logged.post(
        reverse("budgets:add_recurring"), _payload(fixed_cat, wallet, default_amount="abc")
    )
    assert resp.status_code == 400
    assert RecurringExpense.objects.count() == 0


def test_add_recurring_rejects_non_fixed_category(client_logged, user, wallet):
    from django.urls import reverse

    ant = Category.objects.create(owner=user, name="Café", kind=Category.Kind.ANT)
    resp = client_logged.post(reverse("budgets:add_recurring"), _payload(ant, wallet))
    assert resp.status_code == 400
    assert RecurringExpense.objects.count() == 0


def test_update_recurring_changes_fields(client_logged, user, wallet, fixed_cat):
    from django.urls import reverse

    r = RecurringExpense.objects.create(
        owner=user, name="Gym", default_amount=Decimal("10000"),
        category=fixed_cat, wallet=wallet, day_of_month=1,
    )
    resp = client_logged.post(
        reverse("budgets:update_recurring", args=[r.id]),
        _payload(fixed_cat, wallet, name="Gimnasio", default_amount="25000", day_of_month="5"),
    )
    assert resp.status_code == 200
    r.refresh_from_db()
    assert r.name == "Gimnasio"
    assert r.default_amount == Decimal("25000")
    assert r.day_of_month == 5


def test_toggle_recurring_flips_active(client_logged, user, wallet, fixed_cat):
    from django.urls import reverse

    r = RecurringExpense.objects.create(
        owner=user, name="Gym", default_amount=Decimal("10000"),
        category=fixed_cat, wallet=wallet, is_active=True,
    )
    client_logged.post(reverse("budgets:toggle_recurring", args=[r.id]))
    r.refresh_from_db()
    assert r.is_active is False


def test_delete_recurring_keeps_existing_month_rows(client_logged, user, wallet, fixed_cat):
    from django.urls import reverse
    from django.utils import timezone

    from apps.budgets.services import ensure_month_fixed

    r = RecurringExpense.objects.create(
        owner=user, name="Gym", default_amount=Decimal("10000"),
        category=fixed_cat, wallet=wallet,
    )
    period = timezone.localdate().strftime("%Y-%m")
    ensure_month_fixed(user, period)
    assert Transaction.objects.filter(owner=user, recurring_expense=r).count() == 1

    client_logged.post(reverse("budgets:delete_recurring", args=[r.id]))
    assert RecurringExpense.objects.filter(pk=r.id).count() == 0
    # The already-generated row stays, just unlinked (SET_NULL).
    tx = Transaction.objects.get(owner=user, period=period)
    assert tx.recurring_expense_id is None


def test_recurring_views_require_login(client, user, wallet, fixed_cat):
    from django.urls import reverse

    resp = client.post(reverse("budgets:add_recurring"), _payload(fixed_cat, wallet))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


def test_user_cannot_touch_another_users_template(
    client_logged, django_user_model, wallet, fixed_cat
):
    from django.urls import reverse

    other = django_user_model.objects.create_user(username="otro", password="x")
    other_wallet = Wallet.objects.create(owner=other, name="X", kind=Wallet.Kind.BANK)
    other_cat = Category.objects.create(owner=other, name="Alq", kind=Category.Kind.FIXED)
    r = RecurringExpense.objects.create(
        owner=other, name="Ajeno", default_amount=Decimal("1"),
        category=other_cat, wallet=other_wallet,
    )
    resp = client_logged.post(reverse("budgets:delete_recurring", args=[r.id]))
    assert resp.status_code == 404
    assert RecurringExpense.objects.filter(pk=r.id).exists()


def test_fixed_page_renders(client_logged, user, wallet, fixed_cat):
    from django.urls import reverse

    RecurringExpense.objects.create(
        owner=user, name="Alquiler", default_amount=Decimal("350000"),
        category=fixed_cat, wallet=wallet, day_of_month=10,
    )
    resp = client_logged.get(reverse("budgets:fixed"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Gastos fijos" in body
    assert "Alquiler" in body
