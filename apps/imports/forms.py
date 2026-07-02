from django import forms

from apps.wallets.models import Wallet

from .models import ImportBatch


class ImportUploadForm(forms.Form):
    """Upload a CSV export to import into a wallet."""

    source = forms.ChoiceField(choices=ImportBatch.Source.choices, label="Fuente")
    wallet = forms.ModelChoiceField(queryset=Wallet.objects.none(), label="Billetera")
    file = forms.FileField(label="Archivo CSV")

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields["wallet"].queryset = Wallet.objects.filter(owner=owner, is_active=True)

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = (f.name or "").lower()
        if not name.endswith(".csv"):
            raise forms.ValidationError("Por ahora solo se admiten archivos .csv")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo es demasiado grande (máx. 5 MB).")
        return f
