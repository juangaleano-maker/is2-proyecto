from django.contrib import admin
from .models import Cotizacion

@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ('moneda_origen', 'moneda_destino', 'compra', 'venta', 'fecha', 'activo')
    list_filter = ('moneda_origen', 'moneda_destino', 'activo', 'fecha')
    search_fields = ('moneda_origen', 'moneda_destino')
