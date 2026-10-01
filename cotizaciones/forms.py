from django import forms
from decimal import Decimal
from .models import Cotizacion, Operacion
from monedas.models import Moneda
from clientes.models import Cliente
from .services import obtener_clientes_asignados_usuario


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


class BaseOperacionForm(forms.ModelForm):
    """
    Formulario base para operaciones de cambio (Venta y Compra).
    Garantiza una interfaz unificada, validaciones de montos y filtrado
    de clientes asignados al usuario en sesión.
    """
    class Meta:
        model = Operacion
        fields = ['cliente', 'moneda', 'monto', 'tasa_aplicada', 'comision']
        widgets = {
            'cliente': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_cliente',
                'required': 'required',
            }),
            'moneda': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_moneda',
                'required': 'required',
            }),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control',
                'id': 'id_monto',
                'step': '0.01',
                'min': '0.01',
                'placeholder': 'Ej. 100.00',
                'required': 'required',
            }),
            'tasa_aplicada': forms.NumberInput(attrs={
                'class': 'form-control',
                'id': 'id_tasa_aplicada',
                'step': '0.01',
                'min': '0.01',
                'placeholder': 'Ej. 7950.00',
                'required': 'required',
            }),
            'comision': forms.NumberInput(attrs={
                'class': 'form-control bg-light',
                'id': 'id_comision',
                'step': '0.01',
                'readonly': 'readonly',
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filtrar clientes asignados al usuario autenticado
        if user:
            qs = obtener_clientes_asignados_usuario(user)
        else:
            qs = Cliente.objects.filter(activo=True)

        self.fields['cliente'].queryset = qs
        self.fields['cliente'].empty_label = "--- Seleccione el cliente asignado ---"
        self.fields['cliente'].label_from_instance = (
            lambda c: f"{c} ({c.documento}) — [{c.get_segmento_display()}]"
        )

        # Monedas activas
        self.fields['moneda'].queryset = Moneda.objects.filter(activa=True).order_by('siglas')
        self.fields['moneda'].empty_label = "--- Seleccione la divisa ---"
        self.fields['moneda'].label_from_instance = (
            lambda m: f"{m.siglas} - {m.nombre}"
        )

        # Campo comision no es requerido en el post inicial ya que se calcula en el backend
        self.fields['comision'].required = False

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto is None or monto <= Decimal('0'):
            raise forms.ValidationError("El monto de la operación debe ser un número positivo mayor a cero.")
        return monto

    def clean_tasa_aplicada(self):
        tasa = self.cleaned_data.get('tasa_aplicada')
        if tasa is None or tasa <= Decimal('0'):
            raise forms.ValidationError("La tasa aplicada debe ser un valor positivo mayor a cero.")
        return tasa

    def clean_cliente(self):
        cliente = self.cleaned_data.get('cliente')
        if not cliente:
            raise forms.ValidationError("Debe seleccionar un cliente asignado válido.")
        if not cliente.activo:
            raise forms.ValidationError("El cliente seleccionado se encuentra inactivo y no puede operar.")
        return cliente


class VentaMonedaForm(BaseOperacionForm):
    """
    Formulario especializado para la Venta de Moneda (IS2-16).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['monto'].widget.attrs.update({
            'placeholder': 'Monto a vender (ej. 100.00)',
            'aria-label': 'Monto de divisa a vender'
        })
        self.fields['tasa_aplicada'].widget.attrs.update({
            'placeholder': 'Tasa de cambio aplicada',
            'aria-label': 'Tasa de cambio acordada/vigente'
        })


class CompraMonedaForm(BaseOperacionForm):
    """
    Formulario especializado para la Compra de Moneda (simétrico a Venta).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['monto'].widget.attrs.update({
            'placeholder': 'Monto a comprar (ej. 100.00)',
            'aria-label': 'Monto de divisa a comprar'
        })

