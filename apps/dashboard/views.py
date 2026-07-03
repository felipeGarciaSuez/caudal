from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.budgets.models import MonthlyBudget
from apps.budgets.services import ensure_month_fixed
from apps.savings.services import saved_ars
from apps.transactions.forms import MonthlyIncomeForm, QuickTransactionForm
from apps.transactions.models import Category, Transaction
from apps.wallets.models import Wallet

PERIOD_FMT = "%Y-%m"


def _current_period() -> str:
    return timezone.localdate().strftime(PERIOD_FMT)


def _shift_period(period: str, months: int) -> str:
    year, month = (int(p) for p in period.split("-"))
    index = (year * 12 + (month - 1)) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _period_label(period: str) -> str:
    names = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    year, month = (int(p) for p in period.split("-"))
    return f"{names[month - 1].capitalize()} {year}"


def _get_or_build_budget(user, period: str) -> MonthlyBudget:
    """Return the period budget; if missing, build (unsaved) with a sensible default."""
    budget = MonthlyBudget.objects.filter(owner=user, period=period).first()
    if budget is None:
        default_income = user.monthly_income_default or 0
        budget = MonthlyBudget(owner=user, period=period, expected_income=default_income)
    return budget


def _default_date_for(period: str) -> date:
    """Today when viewing the current month, else the 1st of that month."""
    if period == _current_period():
        return timezone.localdate()
    year, month = (int(p) for p in period.split("-"))
    return date(year, month, 1)


def _pct(part: Decimal, whole: Decimal) -> int:
    """Integer percentage of part over whole, clamped to 0..100."""
    if not whole:
        return 0
    return max(0, min(100, int((part / whole) * 100)))


def _ant_total(user, period: str) -> Decimal:
    """Total hormiga (ant) spend for a period (own part, excluding review)."""
    total = Transaction.objects.filter(
        owner=user,
        period=period,
        kind=Transaction.Kind.EXPENSE,
        category__kind=Category.Kind.ANT,
        needs_review=False,
    ).aggregate(total=Sum(F("amount") * F("shared_ratio")))["total"] or Decimal("0")
    return Decimal(total).quantize(Decimal("0.01"))


def _pct_change(current: Decimal, previous: Decimal) -> int | None:
    """Signed integer percent change of current vs previous; None if no base."""
    if not previous:
        return None
    return int(((current - previous) / previous) * 100)


# A checklist row is a manually-entered fixed obligation (recurring template or
# an ad-hoc "big expense" you typed in) — never an imported one. This is what
# keeps a multi-line card statement from flooding the checklist with dozens of
# editable rows: imported fixed-categorized charges (e.g. subscriptions) fall
# through to `big_rows` (aggregated by category) instead.
_CHECKLIST_Q = Q(category__kind=Category.Kind.FIXED, source=Transaction.Source.MANUAL)


def _group_checklist(fixed_rows: list) -> list[dict]:
    """Cluster checklist rows by category.parent (e.g. "Gastos Vivienda").

    Each group keeps the rows' existing pending-first order; named groups come
    first (alphabetically), ungrouped rows go last. If everything is ungrouped
    this collapses to a single unlabeled group, same look as before grouping.
    """
    groups: dict[int | None, dict] = {}
    order: list[int | None] = []
    for tx in fixed_rows:
        parent = tx.category.parent if tx.category else None
        key = parent.id if parent else None
        if key not in groups:
            groups[key] = {"name": parent.name if parent else None, "rows": []}
            order.append(key)
        groups[key]["rows"].append(tx)
    order.sort(key=lambda k: (k is None, groups[k]["name"] or ""))
    return [groups[k] for k in order]


def _month_context(user, period: str) -> dict:
    budget = _get_or_build_budget(user, period)
    own = F("amount") * F("shared_ratio")  # the part that's actually mine
    # needs_review rows (unconfirmed card items) stay out of the month until reviewed.
    expenses = Transaction.objects.filter(
        owner=user,
        period=period,
        kind=Transaction.Kind.EXPENSE,
        needs_review=False,
    )

    # The star: the big-expenses checklist (Excel-style "did I pay everything?").
    fixed_rows = list(
        expenses.filter(_CHECKLIST_Q)
        .select_related("wallet", "category", "category__parent")
        .order_by("is_paid", "date", "id")
    )

    # Everything else that isn't hormiga: imported fixed-kind (e.g. card
    # subscriptions) and all variable (Súper, etc.). Grouped by category so a big
    # import shows as one line instead of dozens of rows -- BUT a category with a
    # single movement is surfaced as that movement, so it can be ticked/deleted
    # right here (grouped when several, loose when one).
    zero = Decimal("0.00")
    big_txs = (
        expenses.exclude(_CHECKLIST_Q)
        .exclude(category__kind=Category.Kind.ANT)
        .select_related("wallet", "category")
        .order_by("-date", "-id")
    )
    big_groups: dict[int | None, list] = {}
    big_order: list[int | None] = []
    for tx in big_txs:
        big_groups.setdefault(tx.category_id, [])
        if tx.category_id not in big_order:
            big_order.append(tx.category_id)
        big_groups[tx.category_id].append(tx)
    big_rows = []
    for key in big_order:
        txs = big_groups[key]
        cat = txs[0].category
        big_rows.append(
            {
                "category": key,
                "category__name": cat.name if cat else None,
                "category__kind": cat.kind if cat else None,
                "category__icon": cat.icon if cat else None,
                "total": sum((t.own_amount for t in txs), zero),
                "count": len(txs),
                # The Transaction itself when there's exactly one; None otherwise.
                "single": txs[0] if len(txs) == 1 else None,
            }
        )
    big_rows.sort(key=lambda r: r["total"], reverse=True)

    # Hormiga: small/frequent spend, kept fully separate from "grandes".
    ant_rows = list(
        expenses.filter(category__kind=Category.Kind.ANT)
        .values("category", "category__name", "category__kind", "category__icon")
        .annotate(total=Sum(own), count=Count("id"))
        .order_by("-total")
    )
    # Individual movements per category, for the "ver individualmente" toggle.
    ant_movements: dict[int | None, list] = {}
    for tx in (
        expenses.filter(category__kind=Category.Kind.ANT)
        .select_related("wallet", "category")
        .order_by("-date", "-id")
    ):
        ant_movements.setdefault(tx.category_id, []).append(tx)
    for row in ant_rows:
        row["movements"] = ant_movements.get(row["category"], [])

    fixed_total = sum((t.own_amount for t in fixed_rows), zero)
    fixed_paid = sum((t.own_amount for t in fixed_rows if t.is_paid), zero)
    fixed_pending = fixed_total - fixed_paid
    paid_count = sum(1 for t in fixed_rows if t.is_paid)

    q2 = Decimal("0.01")
    big_total = sum((r["total"] for r in big_rows), zero).quantize(q2)
    grandes_total = fixed_total + big_total
    ant_total = sum((r["total"] for r in ant_rows), zero).quantize(q2)

    total_spent = grandes_total + ant_total
    # Compras de dólares con billetera ya están adentro de total_spent (categoría
    # Ahorro, un gasto grande más). saved_ars solo devuelve el crédito de un
    # rescate neto (venta de dólares), que no tiene Transaction propia.
    saved = saved_ars(user, period)
    income = budget.expected_income or zero
    used = total_spent + saved
    remaining = income - used

    # --- Hormiga panel (retrospectivo): comparación mes a mes -----------------
    prev_period = _shift_period(period, -1)
    ant_prev = _ant_total(user, prev_period)
    # Alert when this month already spent clearly more hormiga than last month.
    ant_alert = ant_prev > zero and ant_total > ant_prev * Decimal("1.15")

    metrics = {
        "income": income,
        "total_spent": total_spent,
        "saved": saved,
        "saved_abs": abs(saved),
        "remaining": remaining,
        "spent_pct": _pct(used, income),
        "over_budget": remaining < 0,
        # checklist (editable, manual only)
        "fixed_total": fixed_total,
        "fixed_paid": fixed_paid,
        "fixed_pending": fixed_pending,
        "fixed_count": len(fixed_rows),
        "fixed_paid_count": paid_count,
        "fixed_all_paid": len(fixed_rows) > 0 and paid_count == len(fixed_rows),
        # big aggregated (imported fixed + variable) and the grandes grand total
        "big_total": big_total,
        "grandes_total": grandes_total,
        # hormiga (retrospectivo)
        "ant": ant_total,
        "ant_prev": ant_prev,
        "ant_vs_prev": _pct_change(ant_total, ant_prev),
        "ant_alert": ant_alert,
    }

    return {
        "period": period,
        "period_label": _period_label(period),
        "prev_period": prev_period,
        "next_period": _shift_period(period, 1),
        "is_current": period == _current_period(),
        "fixed_rows": fixed_rows,
        "fixed_groups": _group_checklist(fixed_rows),
        "big_rows": big_rows,
        "ant_rows": ant_rows,
        "review_count": Transaction.objects.filter(owner=user, needs_review=True).count(),
        "budget": budget,
        "m": metrics,
        "default_date": _default_date_for(period),
        "wallets": Wallet.objects.filter(owner=user, is_active=True),
        # Group-only categories (e.g. "Gastos Vivienda") aren't selectable
        # directly — only their children are.
        "quick_categories": Category.objects.filter(owner=user, children__isnull=True).order_by(
            "kind", "name"
        ),
        "big_categories": Category.objects.filter(
            owner=user,
            kind__in=[Category.Kind.FIXED, Category.Kind.VARIABLE],
            children__isnull=True,
        ).order_by("kind", "name"),
    }


@login_required
def home(request):
    return redirect("dashboard:month", period=_current_period())


@login_required
def settings_home(request):
    """Hub of configuration screens: wallets, categories, rules, fixed expenses."""
    return render(request, "dashboard/settings.html", {"nav_active": "settings"})


@login_required
def month_view(request, period):
    # Auto-generate this month's fixed expenses (pending) for the current month
    # onwards, so the checklist is always there without extra taps.
    if period >= _current_period():
        ensure_month_fixed(request.user, period)
    context = _month_context(request.user, period)
    context["nav_active"] = "month"
    return render(request, "dashboard/month.html", context)


@login_required
@require_POST
def add_transaction(request):
    period = request.POST.get("period") or _current_period()
    form = QuickTransactionForm(request.POST, owner=request.user)
    if not form.is_valid():
        context = _month_context(request.user, period)
        context["form_error"] = "; ".join(
            f"{field}: {', '.join(errs)}" for field, errs in form.errors.items()
        )
        return render(request, "dashboard/_month_body.html", context, status=400)
    tx = form.save()
    # Re-render the body for the period the transaction landed in.
    context = _month_context(request.user, tx.period)
    context["just_added"] = tx
    return render(request, "dashboard/_month_body.html", context)


def _category_detail_context(user, period: str, category_id: int) -> dict:
    if category_id == 0:
        category = None
        rows = Transaction.objects.filter(
            owner=user,
            period=period,
            kind=Transaction.Kind.EXPENSE,
            category__isnull=True,
        )
        title = "Sin categoría"
    else:
        category = get_object_or_404(Category, pk=category_id, owner=user)
        rows = Transaction.objects.filter(owner=user, period=period, category=category)
        title = category.name
    rows = rows.select_related("wallet", "category").order_by("-date", "-id")
    total = rows.aggregate(total=Sum("amount"))["total"] or 0
    return {
        "category": category,
        "category_id": category_id,
        "title": title,
        "period": period,
        "period_label": _period_label(period),
        "rows": rows,
        "total": total,
        "nav_active": "month",
        # For the inline edit form rendered per row.
        "wallets": Wallet.objects.filter(owner=user, is_active=True),
        "edit_categories": Category.objects.filter(owner=user, children__isnull=True).order_by(
            "kind", "name"
        ),
    }


@login_required
def category_detail(request, period, category_id):
    context = _category_detail_context(request.user, period, category_id)
    return render(request, "dashboard/category_detail.html", context)


def _tx_scope_args(request, tx) -> tuple[str, str, int]:
    """Read where a tx action came from, to re-render the right surface."""
    scope = request.POST.get("scope") or "month"
    period = request.POST.get("period") or tx.period
    try:
        category_id = int(request.POST.get("category_id") or 0)
    except (TypeError, ValueError):
        category_id = 0
    return scope, period, category_id


def _render_tx_scope(request, period: str, scope: str, category_id: int):
    """Re-render the month body or the category-detail body after a tx change."""
    if scope == "detail":
        context = _category_detail_context(request.user, period, category_id)
        return render(request, "dashboard/_detail_body.html", context)
    context = _month_context(request.user, period)
    return render(request, "dashboard/_month_body.html", context)


@login_required
@require_POST
def toggle_paid(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id, owner=request.user)
    tx.is_paid = not tx.is_paid
    tx.save(update_fields=["is_paid"])
    scope, period, category_id = _tx_scope_args(request, tx)
    return _render_tx_scope(request, period, scope, category_id)


@login_required
@require_POST
def edit_transaction(request, tx_id):
    """Full edit of a single movement (amount, description, category, wallet, date)."""
    tx = get_object_or_404(Transaction, pk=tx_id, owner=request.user)
    scope, period, category_id = _tx_scope_args(request, tx)
    form = QuickTransactionForm(request.POST, instance=tx, owner=request.user)
    if not form.is_valid():
        message = "; ".join(f"{field}: {', '.join(errs)}" for field, errs in form.errors.items())
        return HttpResponseBadRequest(f"No se pudo guardar: {message}")
    form.save()
    return _render_tx_scope(request, period, scope, category_id)


@login_required
@require_POST
def delete_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id, owner=request.user)
    scope, period, category_id = _tx_scope_args(request, tx)
    tx.delete()
    return _render_tx_scope(request, period, scope, category_id)


@login_required
@require_POST
def update_amount(request, tx_id):
    """Edit the amount of a fixed expense inline (from the month checklist)."""
    tx = get_object_or_404(Transaction, pk=tx_id, owner=request.user)
    raw = (request.POST.get("amount") or "").replace(",", ".")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        return HttpResponseBadRequest("Monto inválido")
    if amount < 0:
        return HttpResponseBadRequest("Monto inválido")
    tx.amount = amount
    tx.save(update_fields=["amount"])
    context = _month_context(request.user, tx.period)
    return render(request, "dashboard/_month_body.html", context)


@login_required
@require_POST
def set_income(request, period):
    form = MonthlyIncomeForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Sueldo inválido")
    MonthlyBudget.objects.update_or_create(
        owner=request.user,
        period=period,
        defaults={"expected_income": form.cleaned_data["expected_income"]},
    )
    context = _month_context(request.user, period)
    return render(request, "dashboard/_month_body.html", context)
