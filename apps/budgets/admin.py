from django.contrib import admin

from .models import MonthlyBudget, RecurringExpense


@admin.register(RecurringExpense)
class RecurringExpenseAdmin(admin.ModelAdmin):
    list_display = ("name", "default_amount", "category", "wallet", "day_of_month", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name",)


@admin.register(MonthlyBudget)
class MonthlyBudgetAdmin(admin.ModelAdmin):
    list_display = ("period", "expected_income", "total_spent", "remaining", "owner")
    search_fields = ("period",)

    @admin.display(description="Gastado")
    def total_spent(self, obj):
        return obj.total_spent

    @admin.display(description="Resto sueldo")
    def remaining(self, obj):
        return obj.remaining
