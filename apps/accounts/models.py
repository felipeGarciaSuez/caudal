from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user.

    Single-user today, but everything hangs off a user FK so the app is
    multi-user-ready without a migration rewrite later.
    """

    monthly_income_default = models.DecimalField(
        "sueldo esperado por defecto",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Sueldo de referencia para meses nuevos. Editable por mes.",
    )
    ant_threshold = models.DecimalField(
        "umbral hormiga",
        max_digits=14,
        decimal_places=2,
        default=Decimal("100000.00"),
        help_text="Un gasto por debajo de este monto se considera hormiga (salvo los fijos).",
    )
    auto_big_expenses = models.BooleanField(
        "gastos grandes automáticos",
        default=True,
        help_text="Clasificar por monto: un gasto que llega al umbral cuenta como grande solo. "
        "Si se apaga, un gasto es grande únicamente cuando se marca a mano.",
    )

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username
