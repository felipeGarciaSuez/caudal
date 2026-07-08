from django.conf import settings
from django.db import models


class CategoryRule(models.Model):
    """Keyword rule: if it appears in a transaction description, assign a category.

    Editable from the admin. First active rule (by priority, then id) that matches wins.
    Unmatched rows stay uncategorised for manual review.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="category_rules",
    )
    keyword = models.CharField(
        "palabra clave",
        max_length=80,
        help_text="Se busca dentro de la descripción (sin distinguir mayúsculas).",
    )
    category = models.ForeignKey(
        "transactions.Category",
        on_delete=models.CASCADE,
        related_name="rules",
    )
    priority = models.IntegerField("prioridad", default=100, help_text="Menor = se evalúa primero.")
    is_active = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "regla de categorización"
        verbose_name_plural = "reglas de categorización"
        ordering = ["priority", "id"]

    def __str__(self):
        return f"{self.keyword} -> {self.category}"


class ImportBatch(models.Model):
    """A CSV/XLSX import run, with dedupe counters."""

    class Source(models.TextChoices):
        MERCADOPAGO = "mercadopago", "Mercado Pago"
        UALA = "uala", "Ualá"
        PERSONALPAY = "personalpay", "Personal Pay"
        BANK_ICBC = "bank_icbc", "Banco ICBC"
        BANK_GALICIA = "bank_galicia", "Banco Galicia"
        CARD_ICBC = "card_icbc", "Tarjeta ICBC"
        GENERIC_CSV = "generic_csv", "CSV genérico"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="import_batches",
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.PROTECT,
        related_name="import_batches",
    )
    source = models.CharField("fuente", max_length=20, choices=Source.choices)
    file = models.FileField("archivo", upload_to="imports/%Y/%m/", blank=True, null=True)
    imported_at = models.DateTimeField("importado el", auto_now_add=True)
    rows_total = models.PositiveIntegerField("filas totales", default=0)
    rows_imported = models.PositiveIntegerField("filas importadas", default=0)
    rows_skipped = models.PositiveIntegerField("filas omitidas (duplicadas)", default=0)
    # False while a preview is awaiting confirmation; True once its rows are saved.
    # Unconfirmed batches are transient (cleaned up when the import page reloads).
    confirmed = models.BooleanField("confirmada", default=True)

    class Meta:
        verbose_name = "importación"
        verbose_name_plural = "importaciones"
        ordering = ["-imported_at"]

    def __str__(self):
        return (
            f"{self.get_source_display()} {self.imported_at:%Y-%m-%d} "
            f"({self.rows_imported}/{self.rows_total})"
        )
