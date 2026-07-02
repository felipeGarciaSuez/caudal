"""Generation of the month's fixed expenses from RecurringExpense templates."""

from __future__ import annotations

import calendar
from datetime import date

from apps.transactions.models import Transaction

from .models import RecurringExpense


def _date_in_period(period: str, day: int) -> date:
    """Build a date for `day` inside `period` (YYYY-MM), clamped to month length."""
    year, month = (int(p) for p in period.split("-"))
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(day, 1), last))


def ensure_month_fixed(user, period: str) -> int:
    """Make sure every active fixed template has a row for `period`.

    Creates missing ones as pending (is_paid=False) with the template's default
    amount, wallet and category. Idempotent: re-running never duplicates. Returns
    the number of rows created.
    """
    templates = RecurringExpense.objects.filter(owner=user, is_active=True).select_related(
        "category", "wallet"
    )
    existing = set(
        Transaction.objects.filter(
            owner=user, period=period, recurring_expense__isnull=False
        ).values_list("recurring_expense_id", flat=True)
    )

    created = 0
    for template in templates:
        if template.id in existing:
            continue
        Transaction.objects.create(
            owner=user,
            date=_date_in_period(period, template.day_of_month),
            amount=template.default_amount,
            kind=Transaction.Kind.EXPENSE,
            wallet=template.wallet,
            category=template.category,
            description=template.name,
            is_paid=False,
            source=Transaction.Source.MANUAL,
            recurring_expense=template,
        )
        created += 1
    return created
