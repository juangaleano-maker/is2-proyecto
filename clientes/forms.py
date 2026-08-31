import re
from django import forms
from .models import Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "tipo_persona", "segmento", "documento",
            "nombre", "apellido",
            "razon_social",
            "email", "telefono", "direccion",
        ]
        widgets = {
            "tipo_persona": forms.Select(attrs={"id": "id_tipo_persona"}),
            "nombre": forms.TextInput(attrs={"data-persona": "fisica"}),
            "apellido": forms.TextInput(attrs={"data-persona": "fisica"}),
            "razon_social": forms.TextInput(attrs={"data-persona": "juridica"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo_persona")
        documento = cleaned_data.get("documento", "")

        if tipo == Cliente.TipoPersona.FISICA:
            if not cleaned_data.get("nombre", "").strip():
                self.add_error("nombre", "El nombre es obligatorio para persona física.")
            if not cleaned_data.get("apellido", "").strip():
                self.add_error("apellido", "El apellido es obligatorio para persona física.")
            if documento and not re.fullmatch(r"\d{6,8}", documento):
                self.add_error(
                    "documento",
                    "La CI debe contener entre 6 y 8 dígitos numéricos (sin puntos ni guiones)."
                )

        elif tipo == Cliente.TipoPersona.JURIDICA:
            if not cleaned_data.get("razon_social", "").strip():
                self.add_error("razon_social", "La razón social es obligatoria para persona jurídica.")
            if documento and not re.fullmatch(r"[A-Za-z0-9\-]{6,20}", documento):
                self.add_error(
                    "documento",
                    "El RUC debe tener entre 6 y 20 caracteres alfanuméricos."
                )

        return cleaned_data

    def clean_documento(self):
        documento = self.cleaned_data.get("documento", "")
        qs = Cliente.objects.filter(documento=documento)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un cliente registrado con este documento.")
        return documento