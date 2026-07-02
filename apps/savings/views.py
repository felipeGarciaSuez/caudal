from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.imports.parsers import ParseError, parse_ar_amount
from apps.wallets.models import Wallet

from . import services
from .models import Asset, SavingsMovement


def _savings_context(user) -> dict:
    portfolio = services.build_portfolio(user)
    movements = (
        SavingsMovement.objects.filter(owner=user)
        .select_related("asset", "from_wallet")
        .order_by("-date", "-id")[:30]
    )
    # asset id -> locations that currently hold that asset (so a sell can only
    # come out of somewhere the dollars actually are).
    holdings_by_asset = {
        row["asset"].id: [name for name, qty in row["locations"] if qty > 0]
        for row in portfolio["rows"]
    }
    return {
        "portfolio": portfolio,
        "dollar_price": services.current_dollar_price(user),
        "movements": movements,
        "assets": Asset.objects.filter(quote_currency="USD").order_by("kind", "symbol"),
        "holdings_by_asset": holdings_by_asset,
        "wallets": Wallet.objects.filter(owner=user, is_active=True),
        "locations": services.known_locations(user),
        "today": timezone.localdate(),
        "nav_active": "savings",
        # The '+' FAB adds a gasto, which lives on the month page.
        "add_href": reverse("dashboard:month", args=[timezone.localdate().strftime("%Y-%m")])
        + "#add-card",
    }


@login_required
def savings_home(request):
    return render(request, "savings/home.html", _savings_context(request.user))


# Operations the UI can record. Buy adds dollars (pesos leave a wallet), sell
# takes them out (pesos come back into a wallet).
_ALLOWED_KINDS = (SavingsMovement.Kind.BUY, SavingsMovement.Kind.SELL)


@login_required
@require_POST
def add_movement(request):
    """Record a buy or a sell: X USD for $Y, at <location>, via <wallet>."""
    user = request.user
    kind = request.POST.get("kind", SavingsMovement.Kind.BUY)
    if kind not in _ALLOWED_KINDS:
        return _error_body(request, "Operación inválida.")
    asset = get_object_or_404(Asset, pk=request.POST.get("asset"), quote_currency="USD")

    try:
        quantity = parse_ar_amount(request.POST.get("quantity"))
        ars_amount = parse_ar_amount(request.POST.get("ars_amount"))
    except ParseError:
        return _error_body(request, "Revisá los montos: cantidad de dólares y pesos.")
    if quantity <= 0 or ars_amount <= 0:
        return _error_body(request, "La cantidad y el monto tienen que ser mayores a 0.")

    location = (request.POST.get("location") or "").strip()
    # A sell can only come out of a place that actually holds those dollars.
    if kind == SavingsMovement.Kind.SELL:
        held = services.location_holdings(user, asset)
        if not held:
            return _error_body(request, f"No tenés {asset.name} para vender.")
        available = held.get(location)
        if available is None:
            return _error_body(request, "Elegí un lugar donde tengas esos dólares.")
        if quantity > available:
            return _error_body(
                request,
                f"Solo tenés US$ {available:.2f} en {location}.",
            )

    when = _parse_date(request.POST.get("date")) or timezone.localdate()
    # from_wallet is the wallet involved: source for a buy, destination for a sell.
    wallet = None
    if request.POST.get("from_wallet"):
        wallet = Wallet.objects.filter(owner=user, pk=request.POST["from_wallet"]).first()

    movement = SavingsMovement.objects.create(
        owner=user,
        date=when,
        kind=kind,
        asset=asset,
        quantity=quantity,
        ars_amount=ars_amount,
        from_wallet=wallet,
        location=location,
    )
    # A buy sourced from a wallet is real money leaving this month: register it
    # as an "Ahorro" gasto grande. No wallet = it came from elsewhere (not the
    # sueldo), so it must not touch the month's expenses.
    if kind == SavingsMovement.Kind.BUY and wallet is not None:
        services.create_ahorro_expense(movement)
    context = _savings_context(user)
    context["just_saved"] = True
    return render(request, "savings/_body.html", context)


@login_required
@require_POST
def set_price(request):
    try:
        price = parse_ar_amount(request.POST.get("price"))
    except ParseError:
        return _error_body(request, "Cotización inválida.")
    if price <= 0:
        return _error_body(request, "La cotización tiene que ser mayor a 0.")
    services.set_dollar_price(price)
    return render(request, "savings/_body.html", _savings_context(request.user))


@login_required
@require_POST
def delete_movement(request, mv_id):
    movement = get_object_or_404(SavingsMovement, pk=mv_id, owner=request.user)
    if movement.linked_expense_id:
        movement.linked_expense.delete()
    movement.delete()
    return render(request, "savings/_body.html", _savings_context(request.user))


def _error_body(request, message: str):
    context = _savings_context(request.user)
    context["form_error"] = message
    return render(request, "savings/_body.html", context, status=400)


def _parse_date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
