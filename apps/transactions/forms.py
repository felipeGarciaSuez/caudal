from django import forms

from apps.wallets.models import Wallet

from .models import Category, Transaction


class QuickTransactionForm(forms.ModelForm):
    """Minimal fast-entry form: amount + category + wallet, date defaults to today."""

    class Meta:
        model = Transaction
        fields = [
            "amount",
            "category",
            "wallet",
            "date",
            "kind",
            "description",
            "is_paid",
            "is_big",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        if owner is not None:
            self.fields["category"].queryset = Category.objects.filter(owner=owner)
            self.fields["wallet"].queryset = Wallet.objects.filter(owner=owner, is_active=True)
        self.fields["category"].required = False
        self.fields["description"].required = False

    def save(self, commit=True):
        tx = super().save(commit=False)
        if self.owner is not None:
            tx.owner = self.owner
        if commit:
            tx.save()
        return tx


class MonthlyIncomeForm(forms.Form):
    """Set/update the expected income (sueldo) for a period."""

    expected_income = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=0, label="Sueldo esperado"
    )
