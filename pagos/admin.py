"""Admin del módulo de pagos."""

from django.contrib import admin

from .models import (
    ComprobanteSIPAP,
    FacturaElectronica,
    MetodoPagoSistema,
    StripeEventoProcesado,
    TicketTransaccion,
)


@admin.register(MetodoPagoSistema)
class MetodoPagoSistemaAdmin(admin.ModelAdmin):
    """Administración del catálogo global de métodos de pago del sistema."""

    list_display = ("nombre", "categoria", "icono", "activo", "creado_en")
    list_filter = ("categoria", "activo")
    search_fields = ("nombre", "descripcion")
    list_editable = ("activo",)
    readonly_fields = ("creado_en", "actualizado_en")
    ordering = ("categoria", "nombre")

    fieldsets = (
        (None, {
            "fields": ("nombre", "categoria", "icono", "activo"),
        }),
        ("Detalles", {
            "fields": ("descripcion", "creado_en", "actualizado_en"),
            "classes": ("collapse",),
        }),
    )


@admin.register(ComprobanteSIPAP)
class ComprobanteSIPAPAdmin(admin.ModelAdmin):
    """Administración de comprobantes SIPAP."""

    list_display = (
        "id",
        "operacion",
        "estado",
        "subido_por",
        "revisado_por",
        "fecha_subida",
        "fecha_revision",
    )
    list_filter = ("estado",)
    search_fields = ("operacion__id", "subido_por__username", "revisado_por__username")
    readonly_fields = ("fecha_subida", "fecha_revision")


@admin.register(StripeEventoProcesado)
class StripeEventoProcesadoAdmin(admin.ModelAdmin):
    """Administración de eventos Stripe procesados."""

    list_display = ("event_id", "tipo_evento", "procesado_en")
    list_filter = ("tipo_evento",)
    search_fields = ("event_id",)
    readonly_fields = ("event_id", "tipo_evento", "procesado_en", "datos_resumen")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TicketTransaccion)
class TicketTransaccionAdmin(admin.ModelAdmin):
    """Administración de tickets de transacción (solo lectura)."""

    list_display = (
        "numero_ticket",
        "operacion",
        "cliente_nombre",
        "monto",
        "moneda_siglas",
        "metodo_pago",
        "cajero",
        "generado_en",
    )
    list_filter = ("metodo_pago", "generado_en")
    search_fields = (
        "numero_ticket",
        "cliente_nombre",
        "cliente_documento",
        "operacion__id",
        "referencia_externa",
    )
    readonly_fields = (
        "numero_ticket",
        "operacion",
        "cliente_nombre",
        "cliente_documento",
        "monto",
        "moneda_siglas",
        "tasa_aplicada",
        "comision",
        "total_neto",
        "metodo_pago",
        "referencia_externa",
        "cajero",
        "generado_en",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FacturaElectronica)
class FacturaElectronicaAdmin(admin.ModelAdmin):
    """
    Administración y auditoría de Facturas Electrónicas (IS2-63 / RF33, RF34).
    Solo lectura para preservar la trazabilidad fiscal.
    """

    list_display = (
        "numero_factura",
        "cdc_corto",
        "operacion",
        "cliente_nombre",
        "total_liquidado",
        "estado",
        "fecha_emision",
    )
    list_filter = ("estado", "condicion_venta", "moneda_siglas", "fecha_emision")
    search_fields = (
        "numero_factura",
        "cdc",
        "cliente_nombre",
        "cliente_documento",
        "operacion__id",
    )
    readonly_fields = (
        "numero_factura",
        "cdc",
        "operacion",
        "ticket",
        "estado",
        "condicion_venta",
        "cliente_nombre",
        "cliente_documento",
        "cliente_email",
        "moneda_siglas",
        "monto",
        "tasa_aplicada",
        "base_imponible",
        "iva_liquidado",
        "total_liquidado",
        "fecha_emision",
        "fecha_procesado",
        "motivo_anulacion",
        "anulada_por",
        "respuesta_simulador",
    )

    def cdc_corto(self, obj):
        if obj.cdc:
            return f"{obj.cdc[:10]}...{obj.cdc[-6:]}"
        return "-"
    cdc_corto.short_description = "CDC"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
