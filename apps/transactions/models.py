from decimal import Decimal

from django.conf import settings
from django.db import models


class Category(models.Model):
    """Spending category, split by behaviour: fixed / variable / ant (hormiga)."""

    class Kind(models.TextChoices):
        FIXED = "fixed", "Fijo"
        VARIABLE = "variable", "Variable"
        ANT = "ant", "Hormiga"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField("nombre", max_length=80)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    icon = models.CharField("ícono", max_length=40, blank=True)
    color = models.CharField("color", max_length=20, blank=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_category_name_per_owner")
        ]

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """The central table: every income, expense or transfer movement."""

    class Kind(models.TextChoices):
        EXPENSE = "expense", "Gasto"
        INCOME = "income", "Ingreso"
        TRANSFER = "transfer", "Transferencia"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORT = "import", "Importación"
        API = "api", "API"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    date = models.DateField("fecha")
    amount = models.DecimalField("monto", max_digits=14, decimal_places=2)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    description = models.CharField("descripción", max_length=255, blank=True)
    is_paid = models.BooleanField("pagado", default=True)

    # Set when this row was generated from a fixed monthly template.
    recurring_expense = models.ForeignKey(
        "budgets.RecurringExpense",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )

    # Shared expenses (e.g. a flat split with a roommate) — phase 3, optional.
    is_shared = models.BooleanField("compartido", default=False)
    shared_ratio = models.DecimalField(
        "proporción propia",
        max_digits=4,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text="Parte que te corresponde (ej. 0.500 para mitad).",
    )

    # Credit-card installments: this row is cuota `current` of `total`.
    installments_current = models.PositiveSmallIntegerField("cuota", null=True, blank=True)
    installments_total = models.PositiveSmallIntegerField("cuotas totales", null=True, blank=True)
    # Imported card rows land here until confirmed (category / shared / kind), so
    # the credit-card summary is never counted at face value.
    needs_review = models.BooleanField("para revisar", default=False)

    source = models.CharField(
        "origen", max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    external_id = models.CharField(  # noqa: DJ001 — NULL needed for the partial unique dedupe constraint
        "id externo",
        max_length=120,
        blank=True,
        null=True,
        help_text="Para deduplicar importaciones.",
    )
    # YYYY-MM, denormalised for fast monthly views.
    period = models.CharField("período", max_length=7, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimiento"
        verbose_name_plural = "movimientos"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "period"]),
            models.Index(fields=["owner", "kind", "period"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "external_id"],
                name="unique_external_id_per_wallet",
                condition=models.Q(external_id__isnull=False),
            )
        ]

    def __str__(self):
        return f"{self.date} {self.get_kind_display()} {self.amount} ({self.description})"

    def save(self, *args, **kwargs):
        # Keep period in sync with date so monthly views never miss a row.
        # str() of a date is ISO (YYYY-MM-DD); slicing also tolerates str dates.
        if self.date:
            self.period = str(self.date)[:7]
        super().save(*args, **kwargs)

    @property
    def own_amount(self) -> Decimal:
        """Amount that is actually mine, after the shared split."""
        if self.is_shared:
            return (self.amount * self.shared_ratio).quantize(Decimal("0.01"))
        return self.amount
