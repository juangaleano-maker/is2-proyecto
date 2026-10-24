from django.contrib import admin
from .models import (
    Cotizacion,
    Operacion,
    AlertaTasa,
    NotificacionTasa,
    Caja,
    StockBilleteCaja,
    SesionCaja,
    MovimientoCaja,
    SaldoSesionMoneda,
    ConteoBilleteSesion,
)

@admin.register(Caja)
class CajaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'nombre', 'sucursal', 'activa', 'esta_abierta', 'fecha_creacion')
    list_filter = ('activa', 'sucursal')
    search_fields = ('nombre', 'numero', 'sucursal')

@admin.register(StockBilleteCaja)
class StockBilleteCajaAdmin(admin.ModelAdmin):
    list_display = ('caja', 'denominacion', 'cantidad', 'subtotal')
    list_filter = ('caja', 'denominacion__moneda')

@admin.register(SesionCaja)
class SesionCajaAdmin(admin.ModelAdmin):
    list_display = ('id', 'caja', 'cajero', 'estado', 'fecha_apertura', 'fecha_cierre', 'monto_inicial', 'diferencia')
    list_filter = ('estado', 'caja', 'fecha_apertura')
    search_fields = ('cajero__username', 'nombre_caja')

@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(admin.ModelAdmin):
    list_display = ('id', 'sesion', 'tipo', 'monto', 'moneda', 'monto_divisa', 'tipo_divisa', 'fecha')
    list_filter = ('tipo', 'tipo_divisa', 'fecha')
    search_fields = ('concepto',)



