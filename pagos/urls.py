"""URLs del módulo de pagos."""

from django.urls import path

from . import views

app_name = "pagos"

urlpatterns = [
    # Webhook Stripe (CSRF-exempt, raw body)
    path("webhooks/stripe/", views.webhook_stripe, name="webhook_stripe"),

    # SIPAP — Flujo del cliente
    path(
        "comprobante/<int:operacion_id>/subir/",
        views.subir_comprobante_sipap,
        name="subir_comprobante_sipap",
    ),

    # SIPAP — Flujo del cajero / administrador
    path(
        "comprobantes/pendientes/",
        views.lista_comprobantes_pendientes,
        name="lista_comprobantes_pendientes",
    ),
    path(
        "comprobantes/<int:comprobante_id>/revisar/",
        views.revisar_comprobante_sipap,
        name="revisar_comprobante_sipap",
    ),

    # Ticket de transacción
    path(
        "ticket/<int:operacion_id>/",
        views.detalle_ticket,
        name="detalle_ticket",
    ),

    # Stripe — Flujo de pago en la web
    path(
        "stripe/<int:operacion_id>/iniciar/",
        views.iniciar_pago_stripe,
        name="iniciar_pago_stripe",
    ),
    path(
        "stripe/<int:operacion_id>/simular/",
        views.simular_pago_stripe,
        name="simular_pago_stripe",
    ),
    # Facturación Electrónica (IS2-63 e IS2-64)
    path(
        "factura/<int:operacion_id>/",
        views.detalle_factura_operacion,
        name="detalle_factura_operacion",
    ),
    path(
        "factura/id/<int:factura_id>/",
        views.detalle_factura,
        name="detalle_factura",
    ),
    path(
        "factura/<int:factura_id>/anular/",
        views.anular_factura_view,
        name="anular_factura",
    ),
]
