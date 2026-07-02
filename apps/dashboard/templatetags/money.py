"""es-AR money formatting: thousands with '.', decimals with ','."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value, decimals=2):
    """Format a Decimal/number as es-AR currency text (no symbol).

    1172000.00 -> "1.172.000,00"; None/invalid -> "—".
    """
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"

    quant = Decimal(1).scaleb(-decimals)  # 0.01 for 2 decimals
    amount = amount.quantize(quant, rounding=ROUND_HALF_UP)

    negative = amount < 0
    amount = abs(amount)
    int_part, _, dec_part = f"{amount:.{decimals}f}".partition(".")

    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    formatted = ".".join(groups)
    if decimals:
        formatted = f"{formatted},{dec_part}"
    return f"-{formatted}" if negative else formatted


@register.filter
def money_ars(value, decimals=2):
    """Same as money() but prefixed with '$'."""
    text = money(value, decimals)
    return text if text == "—" else f"$ {text}"
