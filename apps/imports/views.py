from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.transactions.models import Category, Transaction
from apps.wallets.models import Wallet

from .forms import ImportUploadForm
from .models import CategoryRule, ImportBatch
from .services import ParseError, commit_import, prepare_import


def _add_href() -> str:
    """Link for the '+' FAB: current month's manual-add form."""
    period = timezone.localdate().strftime("%Y-%m")
    return reverse("dashboard:month", args=[period]) + "#add-card"


def _statement_review_period(wallet) -> str | None:
    """Period to jump to after importing a card statement: the most recent one
    with unreviewed charges, else the most recent charge overall."""
    base = Transaction.objects.filter(wallet=wallet)
    return (
        base.filter(needs_review=True).order_by("-period").values_list("period", flat=True).first()
        or base.order_by("-period").values_list("period", flat=True).first()
    )


@login_required
def import_view(request):
    # A pending (unconfirmed) batch only exists during the preview step; clear
    # any left over from an abandoned preview so they don't pile up.
    ImportBatch.objects.filter(owner=request.user, confirmed=False).delete()

    error = None
    if request.method == "POST":
        form = ImportUploadForm(request.POST, request.FILES, owner=request.user)
        if form.is_valid():
            wallet = form.cleaned_data["wallet"]
            source = form.cleaned_data["source"]
            upload = form.cleaned_data["file"]
            file_bytes = upload.read()
            upload.seek(0)
            try:
                to_create, rows_total, skipped = prepare_import(
                    owner=request.user, wallet=wallet, source=source, file_bytes=file_bytes
                )
            except ParseError as exc:
                error = str(exc)
            else:
                # Persist the file on a pending batch and show the preview; nothing
                # is imported until the user confirms.
                batch = ImportBatch(
                    owner=request.user,
                    wallet=wallet,
                    source=source,
                    rows_total=rows_total,
                    rows_skipped=skipped,
                    rows_imported=len(to_create),
                    confirmed=False,
                )
                batch.file = upload
                batch.save()
                return render(
                    request,
                    "imports/preview.html",
                    {
                        "batch": batch,
                        "rows": to_create,
                        "skipped": skipped,
                        "nav_active": "import",
                        "add_href": _add_href(),
                    },
                )
    else:
        form = ImportUploadForm(owner=request.user)

    recent = (
        ImportBatch.objects.filter(owner=request.user, confirmed=True)
        .select_related("wallet")
        .annotate(n_txs=Count("transactions"))[:10]
    )
    return render(
        request,
        "imports/import.html",
        {
            "form": form,
            "error": error,
            "recent": recent,
            "nav_active": "import",
            "add_href": _add_href(),
        },
    )


@login_required
@require_POST
def import_confirm(request, batch_id):
    """Persist a previewed import (its pending batch), then go to review/list."""
    batch = get_object_or_404(ImportBatch, pk=batch_id, owner=request.user, confirmed=False)
    file_bytes = batch.file.read() if batch.file else b""
    try:
        to_create, _, _ = prepare_import(
            owner=request.user, wallet=batch.wallet, source=batch.source, file_bytes=file_bytes
        )
    except ParseError:
        batch.delete()
        return redirect("imports:import")
    commit_import(batch=batch, to_create=to_create)

    # A statement import lands its charges as "sin revisar": go straight to review.
    if batch.wallet.kind == Wallet.Kind.CREDIT_CARD and to_create:
        period = _statement_review_period(batch.wallet)
        if period:
            return redirect("dashboard:card_statement", wallet_id=batch.wallet.id, period=period)
    return redirect("imports:import")


@login_required
@require_POST
def import_cancel(request, batch_id):
    """Discard a previewed (still pending) import."""
    ImportBatch.objects.filter(pk=batch_id, owner=request.user, confirmed=False).delete()
    return redirect("imports:import")


@login_required
@require_POST
def import_delete(request, batch_id):
    """Delete a confirmed import and, via CASCADE, all the movements it created."""
    ImportBatch.objects.filter(pk=batch_id, owner=request.user, confirmed=True).delete()
    return redirect("imports:import")


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
