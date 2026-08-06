from django import forms

from .models import IncomeSource


class IncomeSourceForm(forms.ModelForm):
    """Add an income source for a month (name + expected amount)."""

    class Meta:
        model = IncomeSource
        fields = ["name", "expected_amount"]
        labels = {"name": "Fuente", "expected_amount": "Monto esperado"}
