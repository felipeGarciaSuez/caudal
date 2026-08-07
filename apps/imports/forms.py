from django import forms

from apps.wallets.models import Wallet

from .models import ImportBatch

# Fuentes con parser probado que realmente andan hoy. El resto del enum
# ImportBatch.Source queda para datos historicos, pero no se ofrece importar
# (evita cargar un formato que todavia no interpretamos bien).
SUPPORTED_SOURCES = [
    ImportBatch.Source.CARD_ICBC,
    ImportBatch.Source.BANK_ICBC,
    ImportBatch.Source.MERCADOPAGO,
]

# Cada fuente solo tiene sentido con ciertos tipos de billetera (DONDE). Elegir
# una billetera incompatible es lo que hacia que un resumen de tarjeta cayera
# como gastos sueltos en una cuenta bancaria en vez de agruparse.
SOURCE_WALLET_KINDS = {
    ImportBatch.Source.CARD_ICBC: [Wallet.Kind.CREDIT_CARD],
    ImportBatch.Source.BANK_ICBC: [Wallet.Kind.BANK],
    ImportBatch.Source.MERCADOPAGO: [Wallet.Kind.WALLET, Wallet.Kind.BANK],
}


class ImportUploadForm(forms.Form):
    """Upload a CSV/PDF export to import into a wallet."""

    source = forms.ChoiceField(
        choices=[(s.value, s.label) for s in SUPPORTED_SOURCES], label="Fuente"
    )
    wallet = forms.ModelChoiceField(queryset=Wallet.objects.none(), label="Billetera")
    file = forms.FileField(label="Archivo CSV")

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields["wallet"].queryset = Wallet.objects.filter(owner=owner, is_active=True)

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = (f.name or "").lower()
        if not name.endswith((".csv", ".pdf")):
            raise forms.ValidationError("Se admiten archivos .csv o .pdf (resumen de tarjeta).")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo es demasiado grande (máx. 5 MB).")
        return f

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source")
        wallet = cleaned.get("wallet")
        if source and wallet:
            allowed = SOURCE_WALLET_KINDS.get(source, [])
            if wallet.kind not in allowed:
                kinds = ", ".join(str(Wallet.Kind(k).label) for k in allowed)
                source_label = dict(self.fields["source"].choices).get(source, source)
                raise forms.ValidationError(
                    f"{source_label} necesita una billetera de tipo: {kinds}. "
                    f"«{wallet.name}» es {wallet.get_kind_display()}."
                )
        return cleaned
