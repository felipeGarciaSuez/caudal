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
