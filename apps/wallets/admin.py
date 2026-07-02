from django.contrib import admin

from .models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "currency", "is_active", "owner")
    list_filter = ("kind", "is_active", "currency")
    search_fields = ("name",)
