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

from .models import Operacion

class ComprarMonedaForm(forms.ModelForm):
    class Meta:
        model = Operacion
        fields = ['cliente', 'moneda', 'monto', 'tasa_aplicada']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'form-select'}),
            'moneda': forms.Select(attrs={'class': 'form-select'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'tasa_aplicada': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
        }

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto is not None and monto <= 0:
            raise forms.ValidationError("El monto debe ser mayor a 0.")
        return monto

    def clean_tasa_aplicada(self):
        tasa = self.cleaned_data.get('tasa_aplicada')
        if tasa is not None and tasa <= 0:
            raise forms.ValidationError("La tasa aplicada debe ser mayor a 0.")
        return tasa
