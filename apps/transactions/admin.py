from django.contrib import admin

from .models import Category, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    search_fields = ("name",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "kind",
        "amount",
        "wallet",
        "category",
        "is_paid",
        "needs_review",
        "description",
    )
    list_filter = ("kind", "needs_review", "is_paid", "source", "wallet")
    search_fields = ("description", "external_id")
    date_hierarchy = "date"
    list_select_related = ("wallet", "category")
    readonly_fields = ("period", "created_at")
