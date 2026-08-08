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

    # --- Income sources (planned vs received) -------------------------------

    @property
    def income_sources(self):
        return IncomeSource.objects.filter(owner=self.owner, period=self.period)

    @property
    def income_planned(self) -> Decimal:
        """Total expected income for the month = sum of its income sources.

        Falls back to the single ``expected_income`` figure when no sources are
        itemized yet, so months created before this feature keep working.
        """
        total = self.income_sources.aggregate(t=Sum("expected_amount"))["t"]
        if total is None:
            return self.expected_income
        return Decimal(total).quantize(Decimal("0.01"))

    @property
    def remaining(self) -> Decimal:
        """RESTO SUELDO = ingreso esperado del mes − gastos − ahorro del mes.

        El ingreso esperado es la suma de las fuentes del mes (sueldo + extras).
        Ahorrar es un destino del sueldo: no es plata perdida, pero tampoco queda
        disponible para gastar, así que descuenta del resto (se muestra aparte).
        """
        return self.income_planned - self.total_spent - self.total_saved


class IncomeSource(models.Model):
    """One expected income line for a month (salary, freelance, rent...).

    Lets a month document several sources instead of a single number. Their sum
    is the expected income that drives the RESTO SUELDO.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="income_sources",
    )
    period = models.CharField("período", max_length=7)  # YYYY-MM
    name = models.CharField("nombre", max_length=120)
    expected_amount = models.DecimalField("monto esperado", max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "fuente de ingreso"
        verbose_name_plural = "fuentes de ingreso"
        ordering = ["id"]
        indexes = [models.Index(fields=["owner", "period"])]

    def __str__(self):
        return f"{self.period} — {self.name}: {self.expected_amount}"
