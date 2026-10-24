"""Admin del módulo de pagos."""

from django.contrib import admin

from .models import ComprobanteSIPAP, MetodoPagoSistema, StripeEventoProcesado, TicketTransaccion


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
