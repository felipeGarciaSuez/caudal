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

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username
