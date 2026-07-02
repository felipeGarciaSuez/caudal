from decimal import Decimal

from django.conf import settings
from django.db import models


class Asset(models.Model):
    """Catalogue entry for a savings asset (USD cash, USDT, BTC, a CEDEAR…)."""

    class Kind(models.TextChoices):
        FIAT_CASH = "fiat_cash", "Dólar billete"
        STABLECOIN = "stablecoin", "Stablecoin (USDT/USDC)"
        CRYPTO = "crypto", "Cripto"
        STOCK_CEDEAR = "stock_cedear", "Acción / CEDEAR"

    symbol = models.CharField("símbolo", max_length=20, unique=True)
    name = models.CharField("nombre", max_length=80)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    quote_currency = models.CharField("moneda de cotización", max_length=4, default="USD")

    class Meta:
        verbose_name = "activo"
        verbose_name_plural = "activos"
        ordering = ["symbol"]

    def __str__(self):
        return self.symbol

    @property
    def latest_price_ars(self) -> Decimal | None:
        snap = self.price_snapshots.order_by("-fetched_at").first()
        return snap.price_ars if snap else None


class Holding(models.Model):
    """A current holding of an asset, at a location (Belo, Binance, colchón…)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="holdings",
    )
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="holdings")
    location = models.CharField("ubicación", max_length=80)
    # 8 decimals so crypto fits.
    quantity = models.DecimalField("cantidad", max_digits=24, decimal_places=8)
    avg_buy_price = models.DecimalField(
        "precio promedio de compra",
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
    )
    notes = models.CharField("notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "tenencia"
        verbose_name_plural = "tenencias"
        ordering = ["asset__symbol", "location"]

    def __str__(self):
        return f"{self.quantity} {self.asset.symbol} @ {self.location}"

    @property
    def current_value_ars(self) -> Decimal | None:
        price = self.asset.latest_price_ars
        if price is None:
            return None
        return (self.quantity * price).quantize(Decimal("0.01"))


class SavingsMovement(models.Model):
    """Deposit/withdraw/buy/sell/convert — links savings (stock) to flow."""

    class Kind(models.TextChoices):
        DEPOSIT = "deposit", "Aporte"
        WITHDRAW = "withdraw", "Rescate"
        BUY = "buy", "Compra"
        SELL = "sell", "Venta"
        CONVERT = "convert", "Conversión"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="savings_movements",
    )
    date = models.DateField("fecha")
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="movements")
    quantity = models.DecimalField("cantidad", max_digits=24, decimal_places=8)
    price = models.DecimalField(
        "precio de la operación", max_digits=18, decimal_places=8, null=True, blank=True
    )
    # Pesos involved in the operation (what left/entered a wallet). Kept explicit
    # so the RESTO SUELDO discount and the cost basis are exact, not derived from
    # a rounded unit price.
    ars_amount = models.DecimalField(
        "monto en pesos", max_digits=14, decimal_places=2, null=True, blank=True
    )
    # If the deposit came out of ARS in a wallet, it discounts the RESTO SUELDO.
    from_wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="savings_movements",
    )
    # A wallet-sourced buy also creates a real "Ahorro" expense (a gasto grande),
    # so it shows in the month like any other big expense instead of a separate
    # hidden discount. Kept in sync by the view that creates/deletes movements.
    linked_expense = models.OneToOneField(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="savings_movement",
    )
    # Where the asset is kept (colchón, Belo, Binance…). Holdings are derived per
    # (asset, location) by aggregating movements, so this is the "DONDE" of savings.
    location = models.CharField("ubicación", max_length=80, blank=True)
    period = models.CharField("período", max_length=7, db_index=True)
    notes = models.CharField("notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "movimiento de ahorro"
        verbose_name_plural = "movimientos de ahorro"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} {self.get_kind_display()} {self.quantity} {self.asset.symbol}"

    def save(self, *args, **kwargs):
        if self.date:
            self.period = str(self.date)[:7]
        super().save(*args, **kwargs)

    @property
    def unit_price(self) -> Decimal | None:
        """ARS paid per unit, derived from the total when available."""
        if self.ars_amount is not None and self.quantity:
            return (self.ars_amount / self.quantity).quantize(Decimal("0.01"))
        return self.price


class PriceSnapshot(models.Model):
    """A quote for an asset. API when available, manual fallback always allowed."""

    class Source(models.TextChoices):
        API = "api", "API"
        MANUAL = "manual", "Manual"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="price_snapshots")
    price_ars = models.DecimalField("precio en ARS", max_digits=18, decimal_places=4)
    source = models.CharField(
        "fuente", max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    fetched_at = models.DateTimeField("tomado el", auto_now_add=True)

    class Meta:
        verbose_name = "cotización"
        verbose_name_plural = "cotizaciones"
        ordering = ["-fetched_at"]
        indexes = [models.Index(fields=["asset", "-fetched_at"])]

    def __str__(self):
        return f"{self.asset.symbol} = {self.price_ars} ARS ({self.fetched_at:%Y-%m-%d})"
