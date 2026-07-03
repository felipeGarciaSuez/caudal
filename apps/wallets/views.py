from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Wallet


def _current_period() -> str:
    return timezone.localdate().strftime("%Y-%m")


def _wallets_context(user, **extra) -> dict:
    wallets = Wallet.objects.filter(owner=user).order_by("-is_active", "kind", "name")
    ctx = {
        "wallets": wallets,
        "active_count": sum(1 for w in wallets if w.is_active),
        "kinds": Wallet.Kind.choices,
        "credit_kind": Wallet.Kind.CREDIT_CARD,
        "nav_active": "settings",
        "add_href": reverse("dashboard:month", args=[_current_period()]) + "#add-card",
    }
    ctx.update(extra)
    return ctx


@login_required
def wallets_home(request):
    return render(request, "wallets/wallets.html", _wallets_context(request.user))


def _error_body(request, message: str):
    context = _wallets_context(request.user)
    context["form_error"] = message
    return render(request, "wallets/_wallets_body.html", context, status=400)


def _clean_day(raw) -> int | None:
    """Parse an optional 1..31 day; None when empty or out of range."""
    if raw in (None, ""):
        return None
    try:
        day = int(raw)
    except (ValueError, TypeError):
        return None
    return min(max(day, 1), 31)


def _clean_common(request, user, instance=None):
    """Validate fields shared by add/update. Returns (data, error)."""
    name = (request.POST.get("name") or "").strip()
    if not name:
        return None, "Poné un nombre para la billetera."
    dupe = Wallet.objects.filter(owner=user, name__iexact=name)
    if instance is not None:
        dupe = dupe.exclude(pk=instance.pk)
    if dupe.exists():
        return None, f"Ya tenés una billetera llamada {name}."
    kind = request.POST.get("kind")
    if kind not in Wallet.Kind.values:
        return None, "Elegí un tipo de billetera."
    currency = (request.POST.get("currency") or "ARS").strip().upper()[:3] or "ARS"
    data = {
        "name": name,
        "kind": kind,
        "currency": currency,
        "closing_day": None,
        "due_day": None,
    }
    # Closing/due day only apply to credit cards.
    if kind == Wallet.Kind.CREDIT_CARD:
        data["closing_day"] = _clean_day(request.POST.get("closing_day"))
        data["due_day"] = _clean_day(request.POST.get("due_day"))
    return data, None


@login_required
@require_POST
def add_wallet(request):
    data, error = _clean_common(request, request.user)
    if error:
        return _error_body(request, error)
    Wallet.objects.create(owner=request.user, is_active=True, **data)
    context = _wallets_context(request.user, just_saved=True)
    return render(request, "wallets/_wallets_body.html", context)


@login_required
@require_POST
def update_wallet(request, pk):
    wallet = get_object_or_404(Wallet, pk=pk, owner=request.user)
    data, error = _clean_common(request, request.user, instance=wallet)
    if error:
        return _error_body(request, error)
    for field, value in data.items():
        setattr(wallet, field, value)
    wallet.save()
    context = _wallets_context(request.user, just_saved=True)
    return render(request, "wallets/_wallets_body.html", context)


@login_required
@require_POST
def toggle_wallet(request, pk):
    wallet = get_object_or_404(Wallet, pk=pk, owner=request.user)
    wallet.is_active = not wallet.is_active
    wallet.save(update_fields=["is_active"])
    return render(request, "wallets/_wallets_body.html", _wallets_context(request.user))


@login_required
@require_POST
def delete_wallet(request, pk):
    wallet = get_object_or_404(Wallet, pk=pk, owner=request.user)
    try:
        wallet.delete()
    except ProtectedError:
        # It has movements/fixed templates pointing at it (PROTECT). Deleting
        # would lose the "DONDE" of real history, so we block it and suggest
        # pausing instead (an inactive wallet just drops out of the selectors).
        return _error_body(
            request,
            f"No podés borrar {wallet.name}: tiene movimientos o gastos fijos. Pausala mejor.",
        )
    return render(request, "wallets/_wallets_body.html", _wallets_context(request.user))
