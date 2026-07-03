from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.transactions.models import Category, Transaction

from .forms import ImportUploadForm
from .models import CategoryRule, ImportBatch
from .services import ParseError, run_import


def _add_href() -> str:
    """Link for the '+' FAB: current month's manual-add form."""
    period = timezone.localdate().strftime("%Y-%m")
    return reverse("dashboard:month", args=[period]) + "#add-card"


def _review_count(user) -> int:
    return Transaction.objects.filter(owner=user, needs_review=True).count()


@login_required
def import_view(request):
    result = None
    error = None
    if request.method == "POST":
        form = ImportUploadForm(request.POST, request.FILES, owner=request.user)
        if form.is_valid():
            try:
                result = run_import(
                    owner=request.user,
                    wallet=form.cleaned_data["wallet"],
                    source=form.cleaned_data["source"],
                    file=form.cleaned_data["file"],
                )
            except ParseError as exc:
                error = str(exc)
            else:
                form = ImportUploadForm(owner=request.user)  # reset on success
    else:
        form = ImportUploadForm(owner=request.user)

    recent = ImportBatch.objects.filter(owner=request.user).select_related("wallet")[:10]
    return render(
        request,
        "imports/import.html",
        {
            "form": form,
            "result": result,
            "error": error,
            "recent": recent,
            "nav_active": "import",
            "add_href": _add_href(),
            "review_count": _review_count(request.user),
        },
    )


def _review_context(user) -> dict:
    rows = (
        Transaction.objects.filter(owner=user, needs_review=True)
        .select_related("wallet", "category")
        .order_by("-date", "-id")
    )
    return {
        "rows": rows,
        "categories": Category.objects.filter(owner=user).order_by("kind", "name"),
        "review_count": rows.count(),
        "nav_active": "import",
        "add_href": _add_href(),
    }


@login_required
def review_view(request):
    """Confirm imported card items (category / shared split) before they count."""
    return render(request, "imports/review.html", _review_context(request.user))


@login_required
@require_POST
def review_update(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id, owner=request.user, needs_review=True)
    if tx.kind == Transaction.Kind.EXPENSE:
        cat_id = request.POST.get("category")
        tx.category = (
            Category.objects.filter(owner=request.user, pk=cat_id).first() if cat_id else None
        )
    # "Mi parte": 1.000 = todo mío; <1 = compartido.
    try:
        ratio = Decimal((request.POST.get("share") or "1").replace(",", "."))
    except InvalidOperation:
        ratio = Decimal("1")
    ratio = min(max(ratio, Decimal("0")), Decimal("1"))
    tx.shared_ratio = ratio
    tx.is_shared = ratio < 1
    tx.needs_review = False
    tx.save()
    return render(request, "imports/_review_body.html", _review_context(request.user))


@login_required
@require_POST
def review_delete(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id, owner=request.user, needs_review=True)
    tx.delete()
    return render(request, "imports/_review_body.html", _review_context(request.user))


# --- Reglas de categorización (auto-categorización al importar) ---------------


def _rules_context(user, **extra) -> dict:
    rules = (
        CategoryRule.objects.filter(owner=user)
        .select_related("category")
        .order_by("priority", "id")
    )
    ctx = {
        "rules": rules,
        "categories": Category.objects.filter(owner=user, children__isnull=True).order_by(
            "kind", "name"
        ),
        "active_count": sum(1 for r in rules if r.is_active),
        "nav_active": "settings",
        "add_href": reverse("dashboard:month", args=[timezone.localdate().strftime("%Y-%m")])
        + "#add-card",
    }
    ctx.update(extra)
    return ctx


def _rules_error(request, message: str):
    context = _rules_context(request.user)
    context["form_error"] = message
    return render(request, "imports/_rules_body.html", context, status=400)


def _clean_rule(request, user):
    """Validate a rule's fields. Returns (data, error)."""
    keyword = (request.POST.get("keyword") or "").strip()
    if not keyword:
        return None, "Poné una palabra clave (lo que aparece en la descripción)."
    cat_id = request.POST.get("category")
    category = Category.objects.filter(owner=user, pk=cat_id).first() if cat_id else None
    if category is None:
        return None, "Elegí a qué categoría manda la regla."
    try:
        priority = int(request.POST.get("priority") or 100)
    except (TypeError, ValueError):
        priority = 100
    return {"keyword": keyword, "category": category, "priority": priority}, None


@login_required
def rules_home(request):
    return render(request, "imports/rules.html", _rules_context(request.user))


@login_required
@require_POST
def add_rule(request):
    data, error = _clean_rule(request, request.user)
    if error:
        return _rules_error(request, error)
    CategoryRule.objects.create(owner=request.user, is_active=True, **data)
    return render(
        request, "imports/_rules_body.html", _rules_context(request.user, just_saved=True)
    )


@login_required
@require_POST
def update_rule(request, pk):
    rule = get_object_or_404(CategoryRule, pk=pk, owner=request.user)
    data, error = _clean_rule(request, request.user)
    if error:
        return _rules_error(request, error)
    for field, value in data.items():
        setattr(rule, field, value)
    rule.save()
    return render(
        request, "imports/_rules_body.html", _rules_context(request.user, just_saved=True)
    )


@login_required
@require_POST
def toggle_rule(request, pk):
    rule = get_object_or_404(CategoryRule, pk=pk, owner=request.user)
    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active"])
    return render(request, "imports/_rules_body.html", _rules_context(request.user))


@login_required
@require_POST
def delete_rule(request, pk):
    rule = get_object_or_404(CategoryRule, pk=pk, owner=request.user)
    rule.delete()
    return render(request, "imports/_rules_body.html", _rules_context(request.user))
