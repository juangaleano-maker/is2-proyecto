from django import forms
from .models import Cotizacion

class CotizacionForm(forms.ModelForm):
    class Meta:
        model = Cotizacion
        fields = ['moneda_origen', 'moneda_destino', 'compra', 'venta']
        widgets = {
            'moneda_origen': forms.Select(attrs={'class': 'form-select'}),
            'moneda_destino': forms.Select(attrs={'class': 'form-select'}),
            'compra': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'venta': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
