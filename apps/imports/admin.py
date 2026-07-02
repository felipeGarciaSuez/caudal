from django.contrib import admin

from .models import CategoryRule, ImportBatch


@admin.register(CategoryRule)
class CategoryRuleAdmin(admin.ModelAdmin):
    list_display = ("keyword", "category", "priority", "is_active", "owner")
    list_filter = ("is_active", "category__kind")
    search_fields = ("keyword",)
    list_editable = ("priority", "is_active")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "wallet",
        "imported_at",
        "rows_total",
        "rows_imported",
        "rows_skipped",
    )
    list_filter = ("source",)
    readonly_fields = ("imported_at", "rows_total", "rows_imported", "rows_skipped")
