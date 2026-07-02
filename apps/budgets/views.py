from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.transactions.models import Category
from apps.wallets.models import Wallet

from .models import RecurringExpense
from .services import ensure_month_fixed


def _current_period() -> str:
    return timezone.localdate().strftime("%Y-%m")


def _parse_amount(raw) -> Decimal | None:
    """Parse a user-typed amount (a plain number input, comma tolerated); None if invalid."""
    try:
        amount = Decimal((raw or "").replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return amount if amount >= 0 else None


def _fixed_context(user, **extra) -> dict:
    recurring = (
        RecurringExpense.objects.filter(owner=user)
        .select_related("category", "wallet")
        .order_by("-is_active", "day_of_month", "name")
    )
    ctx = {
        "recurring": recurring,
        "active_count": sum(1 for r in recurring if r.is_active),
        # Only fixed leaf categories: a recurring expense feeds the month checklist,
        # which is fixed + manual. Group-only parents aren't selectable.
        "categories": Category.objects.filter(
            owner=user, kind=Category.Kind.FIXED, children__isnull=True
        ).order_by("name"),
        "wallets": Wallet.objects.filter(owner=user, is_active=True),
        "nav_active": "month",
        # The '+' FAB adds a loose expense on the current month page.
        "add_href": reverse("dashboard:month", args=[_current_period()]) + "#add-card",
    }
    ctx.update(extra)
    return ctx


@login_required
def fixed_home(request):
    return render(request, "budgets/fixed.html", _fixed_context(request.user))


def _error_body(request, message: str):
    context = _fixed_context(request.user)
    context["form_error"] = message
    return render(request, "budgets/_fixed_body.html", context, status=400)


def _clean_common(request, user):
    """Validate the fields shared by add/update. Returns (data, error)."""
    name = (request.POST.get("name") or "").strip()
    if not name:
        return None, "Poné un nombre para el gasto fijo."
    amount = _parse_amount(request.POST.get("default_amount"))
    if amount is None:
        return None, "Revisá el monto."
    try:
        day = int(request.POST.get("day_of_month") or 1)
    except (ValueError, TypeError):
        return None, "El día del mes no es válido."
    day = min(max(day, 1), 31)
    category = Category.objects.filter(
        owner=user, pk=request.POST.get("category"), kind=Category.Kind.FIXED
    ).first()
    if category is None:
        return None, "Elegí una categoría fija."
    wallet = Wallet.objects.filter(
        owner=user, pk=request.POST.get("wallet"), is_active=True
    ).first()
    if wallet is None:
        return None, "Elegí una billetera."
    data = {
        "name": name,
        "default_amount": amount,
        "day_of_month": day,
        "category": category,
        "wallet": wallet,
    }
    return data, None


@login_required
@require_POST
def add_recurring(request):
    data, error = _clean_common(request, request.user)
    if error:
        return _error_body(request, error)
    RecurringExpense.objects.create(owner=request.user, is_active=True, **data)
    # Make it show up right away on the current (and future) month checklist.
    ensure_month_fixed(request.user, _current_period())
    context = _fixed_context(request.user, just_saved=True)
    return render(request, "budgets/_fixed_body.html", context)


@login_required
@require_POST
def update_recurring(request, pk):
    template = get_object_or_404(RecurringExpense, pk=pk, owner=request.user)
    data, error = _clean_common(request, request.user)
    if error:
        return _error_body(request, error)
    for field, value in data.items():
        setattr(template, field, value)
    template.save()
    context = _fixed_context(request.user, just_saved=True)
    return render(request, "budgets/_fixed_body.html", context)


@login_required
@require_POST
def toggle_recurring(request, pk):
    template = get_object_or_404(RecurringExpense, pk=pk, owner=request.user)
    template.is_active = not template.is_active
    template.save(update_fields=["is_active"])
    # Turning one back on should re-seed it into the current month checklist.
    if template.is_active:
        ensure_month_fixed(request.user, _current_period())
    return render(request, "budgets/_fixed_body.html", _fixed_context(request.user))


@login_required
@require_POST
def delete_recurring(request, pk):
    template = get_object_or_404(RecurringExpense, pk=pk, owner=request.user)
    # Already-generated month rows keep existing (recurring_expense is SET_NULL);
    # deleting the template only stops future auto-generation.
    template.delete()
    return render(request, "budgets/_fixed_body.html", _fixed_context(request.user))
