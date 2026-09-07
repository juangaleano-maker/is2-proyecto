from django import forms
from .models import Moneda

class MonedaForm(forms.ModelForm):
    class Meta:
        model = Moneda
        fields = ['nombre', 'siglas']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Real Brasileño',
                'style': 'width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px;'
            }),
            'siglas': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. BRL',
                'style': 'width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; text-transform: uppercase;'
            }),
        }
        labels = {
            'nombre': 'Nombre de la Moneda',
            'siglas': 'Código / Siglas',
        }
        error_messages = {
            'nombre': {
                'required': 'El nombre de la moneda es obligatorio.',
                'unique': 'Ya existe una moneda registrada con este nombre.',
            },
            'siglas': {
                'required': 'El código/siglas de la moneda es obligatorio.',
                'unique': 'Ya existe una moneda registrada con este código/siglas.',
            },
        }

    def clean_siglas(self):
        siglas = self.cleaned_data.get('siglas')
        if siglas:
            return siglas.strip().upper()
        return siglas

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if nombre:
            return nombre.strip()
        return nombre


class MonedaEditForm(MonedaForm):
    """
    Formulario de edición de moneda. Hereda de MonedaForm
    y acepta una instancia existente para actualizarla.
    Los mensajes de error de unicidad excluyen el registro actual.
    """
    class Meta(MonedaForm.Meta):
        pass  # Hereda todos los campos, widgets y mensajes de MonedaForm
