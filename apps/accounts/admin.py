from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CaudalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Caudal", {"fields": ("monthly_income_default",)}),)
    list_display = ("username", "email", "first_name", "is_staff")
