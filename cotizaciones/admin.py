from django.contrib import admin
from .models import Cotizacion, Operacion, AlertaTasa, NotificacionTasa

@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ('moneda_origen', 'moneda_destino', 'compra', 'venta', 'fecha', 'activo')
    list_filter = ('moneda_origen', 'moneda_destino', 'activo', 'fecha')
    search_fields = ('moneda_origen__nombre', 'moneda_origen__siglas', 'moneda_destino__nombre', 'moneda_destino__siglas')

@admin.register(Operacion)
class OperacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'moneda', 'tipo', 'monto', 'tasa_aplicada', 'comision', 'estado', 'fecha', 'registrado_por')
    list_filter = ('tipo', 'estado', 'moneda', 'fecha')
    search_fields = ('cliente__nombre', 'cliente__apellido', 'cliente__razon_social', 'cliente__documento', 'moneda__siglas')
    readonly_fields = ('fecha',)

@admin.register(AlertaTasa)
class AlertaTasaAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'moneda', 'tipo', 'valor_objetivo', 'activa', 'fecha_creacion')
    list_filter = ('tipo', 'activa', 'moneda')
    search_fields = ('usuario__username', 'moneda__siglas')

@admin.register(NotificacionTasa)
class NotificacionTasaAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'moneda', 'titulo', 'tasa_compra', 'tasa_venta', 'leida', 'fecha_actualizacion')
    list_filter = ('leida', 'moneda', 'fecha_creacion')
    search_fields = ('usuario__username', 'titulo', 'mensaje', 'moneda__siglas')


