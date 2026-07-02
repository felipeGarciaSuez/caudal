"""Savings/portfolio logic: holdings and net worth are derived from the
movement log (each purchase the user records), never kept by hand.

Amounts in ARS use Decimal. Quantities keep 8 decimals so crypto fits later.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from apps.transactions.models import Category, Transaction

from .models import Asset, PriceSnapshot, SavingsMovement

ZERO = Decimal("0")
Q2 = Decimal("0.01")

AHORRO_CATEGORY_NAME = "Ahorro"

# Movements that add the asset to the stash vs. that take it out.
ADD_KINDS = (SavingsMovement.Kind.BUY, SavingsMovement.Kind.DEPOSIT)
SUB_KINDS = (SavingsMovement.Kind.SELL, SavingsMovement.Kind.WITHDRAW)

# Assets whose quantity is denominated 1:1 in dollars (so "how many USD" = sum
# of quantity). Crypto/stocks are not, and are excluded from the USD headline.
USD_1TO1_KINDS = (Asset.Kind.FIAT_CASH, Asset.Kind.STABLECOIN)


def _sign(kind: str) -> Decimal:
    if kind in ADD_KINDS:
        return Decimal("1")
    if kind in SUB_KINDS:
        return Decimal("-1")
    return ZERO  # convert: handled elsewhere, ignored for holdings for now


def build_portfolio(user) -> dict:
    """Aggregate every movement into per-asset holdings, cost and valuation."""
    movements = SavingsMovement.objects.filter(owner=user).select_related("asset")

    accum: dict[int, dict] = {}
    locations: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for m in movements:
        sign = _sign(m.kind)
        asset = m.asset
        data = accum.setdefault(
            asset.id, {"asset": asset, "qty": ZERO, "buy_qty": ZERO, "buy_ars": ZERO}
        )
        data["qty"] += sign * m.quantity
        if m.kind in ADD_KINDS:
            data["buy_qty"] += m.quantity
            data["buy_ars"] += m.ars_amount or ZERO
        locations[asset.id][m.location or "Sin ubicar"] += sign * m.quantity

    rows = []
    total_value = ZERO
    total_cost = ZERO
    total_usd = ZERO
    priced_value = False
    for asset_id, data in accum.items():
        asset = data["asset"]
        qty = data["qty"]
        if qty <= 0:
            continue  # nothing left (fully sold or never held)
        avg_price = (data["buy_ars"] / data["buy_qty"]).quantize(Q2) if data["buy_qty"] else None
        price = asset.latest_price_ars
        value = (qty * price).quantize(Q2) if price is not None else None
        cost = (avg_price * qty).quantize(Q2) if avg_price is not None else None
        pnl = value - cost if (value is not None and cost is not None) else None
        loc_rows = sorted(
            ((name, q) for name, q in locations[asset_id].items() if q != 0),
            key=lambda t: t[1],
            reverse=True,
        )
        rows.append(
            {
                "asset": asset,
                "qty": qty,
                "avg_price": avg_price,
                "price": price,
                "value_ars": value,
                "cost_ars": cost,
                "pnl_ars": pnl,
                "locations": loc_rows,
            }
        )
        if value is not None:
            total_value += value
            priced_value = True
        if cost is not None:
            total_cost += cost
        if asset.kind in USD_1TO1_KINDS:
            total_usd += qty

    rows.sort(key=lambda r: r["value_ars"] or ZERO, reverse=True)
    total_pnl = total_value - total_cost if priced_value else None
    return {
        "rows": rows,
        "total_value_ars": total_value if priced_value else None,
        "total_cost_ars": total_cost,
        "total_pnl_ars": total_pnl,
        "total_usd": total_usd,
        "has_price": priced_value,
    }


def location_holdings(user, asset) -> dict[str, Decimal]:
    """Current net quantity of ``asset`` per location (only positive balances)."""
    result: dict[str, Decimal] = {}
    for row in build_portfolio(user)["rows"]:
        if row["asset"].id == asset.id:
            result = {name: qty for name, qty in row["locations"] if qty > 0}
            break
    return result


def ahorro_category(user):
    """The "Ahorro" category: a savings buy counts as a gasto grande (VARIABLE)."""
    cat, _ = Category.objects.get_or_create(
        owner=user,
        name=AHORRO_CATEGORY_NAME,
        defaults={"kind": Category.Kind.VARIABLE, "icon": "piggy-bank"},
    )
    return cat


def create_ahorro_expense(movement: SavingsMovement):
    """Create (and link) the "Ahorro" expense for a wallet-sourced buy.

    This is what makes a dollar purchase show up as a real gasto grande in the
    month, instead of a separate hidden RESTO discount.
    """
    tx = Transaction.objects.create(
        owner=movement.owner,
        date=movement.date,
        amount=movement.ars_amount,
        kind=Transaction.Kind.EXPENSE,
        wallet=movement.from_wallet,
        category=ahorro_category(movement.owner),
        description=f"Compra de dólares ({movement.asset.symbol})",
        is_paid=True,
        source=Transaction.Source.MANUAL,
    )
    movement.linked_expense = tx
    movement.save(update_fields=["linked_expense"])
    return tx


def saved_ars(user, period: str) -> Decimal:
    """Pesos credited back to the RESTO SUELDO from net dollar sells this period.

    Buys no longer discount here: a wallet-sourced buy creates its own "Ahorro"
    expense Transaction (see `create_ahorro_expense`), already counted through
    the normal gasto-grande pipeline. Only sells still need a manual credit,
    since selling has no automatic income Transaction. Always <= 0 (a credit),
    or 0 if there was no net sell.
    """
    sold = (
        SavingsMovement.objects.filter(
            owner=user,
            period=period,
            kind__in=list(SUB_KINDS),
            from_wallet__isnull=False,
        ).aggregate(total=Sum("ars_amount"))["total"]
        or ZERO
    )
    return (-Decimal(sold)).quantize(Q2)


def current_dollar_price(user) -> Decimal | None:
    """Latest manually-set dollar price (any USD asset)."""
    snap = PriceSnapshot.objects.filter(asset__quote_currency="USD").order_by("-fetched_at").first()
    return snap.price_ars if snap else None


def set_dollar_price(price: Decimal) -> int:
    """Store a manual quote for every USD-denominated asset. Returns count."""
    count = 0
    for asset in Asset.objects.filter(quote_currency="USD"):
        PriceSnapshot.objects.create(
            asset=asset, price_ars=price, source=PriceSnapshot.Source.MANUAL
        )
        count += 1
    return count


def known_locations(user) -> list[str]:
    """Distinct non-empty locations the user has already used."""
    return sorted(
        {
            loc
            for loc in SavingsMovement.objects.filter(owner=user)
            .exclude(location="")
            .values_list("location", flat=True)
        }
    )
