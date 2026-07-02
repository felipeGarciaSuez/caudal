from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Sum

from apps.transactions.models import Category, Transaction

OWN_AMOUNT = F("amount") * F("shared_ratio")  # amount that is actually mine


class RecurringExpense(models.Model):
    """Template for a fixed monthly expense (rent, utilities, subscriptions)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recurring_expenses",
    )
    name = models.CharField("nombre", max_length=120)
    default_amount = models.DecimalField("monto por defecto", max_digits=14, decimal_places=2)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="recurring_expenses"
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.PROTECT,
        related_name="recurring_expenses",
    )
    day_of_month = models.PositiveSmallIntegerField("día del mes", default=1)
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "gasto fijo recurrente"
        verbose_name_plural = "gastos fijos recurrentes"
        ordering = ["day_of_month", "name"]

    def __str__(self):
        return self.name


class MonthlyBudget(models.Model):
    """A monthly period: expected income + computed RESTO SUELDO."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="monthly_budgets",
    )
    period = models.CharField("período", max_length=7)  # YYYY-MM
    expected_income = models.DecimalField("sueldo esperado", max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "presupuesto mensual"
        verbose_name_plural = "presupuestos mensuales"
        ordering = ["-period"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "period"], name="unique_budget_per_owner_period"
            )
        ]

    def __str__(self):
        return f"{self.period} — {self.expected_income}"

    # --- Computed figures (not columns) -------------------------------------

    def _expense_qs(self):
        # needs_review rows (unconfirmed card items) don't count until reviewed.
        return Transaction.objects.filter(
            owner=self.owner,
            period=self.period,
            kind=Transaction.Kind.EXPENSE,
            needs_review=False,
        )

    def _sum(self, qs) -> Decimal:
        # Shared expenses count only for the owner's part (amount * shared_ratio).
        total = qs.aggregate(total=Sum(OWN_AMOUNT))["total"] or Decimal("0")
        return Decimal(total).quantize(Decimal("0.01"))

    @property
    def total_spent(self) -> Decimal:
        return self._sum(self._expense_qs())

    @property
    def total_fixed(self) -> Decimal:
        return self._sum(self._expense_qs().filter(category__kind=Category.Kind.FIXED))

    @property
    def total_variable(self) -> Decimal:
        return self._sum(self._expense_qs().filter(category__kind=Category.Kind.VARIABLE))

    @property
    def total_ant(self) -> Decimal:
        return self._sum(self._expense_qs().filter(category__kind=Category.Kind.ANT))

    @property
    def actual_income(self) -> Decimal:
        return self._sum(
            Transaction.objects.filter(
                owner=self.owner,
                period=self.period,
                kind=Transaction.Kind.INCOME,
            )
        )

    @property
    def total_saved(self) -> Decimal:
        """Pesos que se fueron a ahorro este mes (aportes/compras de dólares)."""
        from apps.savings.services import saved_ars

        return saved_ars(self.owner, self.period)

    @property
    def remaining(self) -> Decimal:
        """RESTO SUELDO = sueldo esperado − gastos − ahorro del mes.

        Ahorrar es un destino del sueldo: no es plata perdida, pero tampoco queda
        disponible para gastar, así que descuenta del resto (se muestra aparte).
        """
        return self.expected_income - self.total_spent - self.total_saved
