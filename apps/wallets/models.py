from django.conf import settings
from django.db import models


class Wallet(models.Model):
    """A means of payment — the Excel 'DONDE' column.

    Bank account, virtual wallet (MP/Ualá/Personal Pay), cash or credit card.
    """

    class Kind(models.TextChoices):
        BANK = "bank", "Banco"
        WALLET = "wallet", "Billetera virtual"
        CASH = "cash", "Efectivo"
        CREDIT_CARD = "credit_card", "Tarjeta de crédito"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallets",
    )
    name = models.CharField("nombre", max_length=80)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    currency = models.CharField("moneda", max_length=3, default="ARS")
    is_active = models.BooleanField("activa", default=True)

    # Only meaningful when kind == credit_card.
    closing_day = models.PositiveSmallIntegerField("día de cierre", null=True, blank=True)
    due_day = models.PositiveSmallIntegerField("día de vencimiento", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "billetera"
        verbose_name_plural = "billeteras"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_wallet_name_per_owner")
        ]

    def __str__(self):
        return self.name

    @property
    def is_credit_card(self) -> bool:
        return self.kind == self.Kind.CREDIT_CARD


class CardStatement(models.Model):
    """Paid/pending state of a credit-card statement for a month.

    A credit card is one payment per month (the statement) made of many charges.
    The charges stay as normal Transactions on the card wallet; this only tracks
    whether the whole statement was paid, so it can be ticked like a fixed expense.
    Created lazily the first time the statement is toggled.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="card_statements",
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.CASCADE,
        related_name="statements",
    )
    period = models.CharField("período", max_length=7, db_index=True)  # YYYY-MM
    is_paid = models.BooleanField("pagado", default=False)

    class Meta:
        verbose_name = "resumen de tarjeta"
        verbose_name_plural = "resúmenes de tarjeta"
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "period"], name="unique_statement_per_wallet_period"
            )
        ]

    def __str__(self):
        return f"{self.wallet.name} {self.period} ({'pagado' if self.is_paid else 'pendiente'})"
