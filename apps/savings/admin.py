from django.contrib import admin

from .models import Asset, Holding, PriceSnapshot, SavingsMovement


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "kind", "quote_currency", "latest_price_ars")
    list_filter = ("kind",)
    search_fields = ("symbol", "name")


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ("asset", "location", "quantity", "current_value_ars", "owner")
    list_filter = ("asset__kind", "location")
    list_select_related = ("asset",)


@admin.register(SavingsMovement)
class SavingsMovementAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "kind",
        "asset",
        "quantity",
        "ars_amount",
        "location",
        "from_wallet",
    )
    list_filter = ("kind", "asset", "location")
    date_hierarchy = "date"
    readonly_fields = ("period",)


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("asset", "price_ars", "source", "fetched_at")
    list_filter = ("source", "asset")
