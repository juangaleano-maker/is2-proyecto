from django.apps import AppConfig


class PagosConfig(AppConfig):
    """Configuración de la aplicación de pagos.

    Gestiona la integración con pasarelas de pago (Stripe, SIPAP),
    los comprobantes adjuntos y los tickets de transacción.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "pagos"
    verbose_name = "Módulo de Pagos"
