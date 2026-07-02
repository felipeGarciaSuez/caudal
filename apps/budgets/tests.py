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
