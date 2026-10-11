"""
Servicio de integración con Stripe (modo test/sandbox).

Implementa la interfaz PasarelaPago usando PaymentIntent de Stripe.
Las claves se leen desde variables de entorno (nunca hardcodeadas).

Configuración requerida en .env::

    STRIPE_SECRET_KEY=sk_test_...
    STRIPE_WEBHOOK_SECRET=whsec_...

Prueba local con Stripe CLI::

    stripe listen --forward-to localhost:8000/pagos/webhooks/stripe/
    stripe trigger payment_intent.succeeded
    stripe trigger payment_intent.payment_failed
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict

from django.conf import settings

from .base import PasarelaPago

logger = logging.getLogger(__name__)


def _get_stripe():
    """
    Importa y configura el cliente de Stripe de forma lazy.

    Raises:
        ImportError: Si el paquete ``stripe`` no está instalado.
        RuntimeError: Si STRIPE_SECRET_KEY no está configurada.
    """
    try:
        import stripe as _stripe
    except ImportError as exc:
        raise ImportError(
            "El paquete 'stripe' no está instalado. "
            "Ejecutá: pip install stripe>=7.0"
        ) from exc

    secret_key = getattr(settings, "STRIPE_SECRET_KEY", None)
    if not secret_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY no está configurada. "
            "Agregá la variable de entorno en tu .env."
        )
    _stripe.api_key = secret_key
    return _stripe


class StripePasarela(PasarelaPago):
    """
    Pasarela de pago Stripe usando PaymentIntent.

    Crea intents de pago en modo test/sandbox y actualiza el estado
    de la operación a través del webhook.
    """

    def crear_pago(self, operacion: Any, **kwargs) -> Dict[str, Any]:
        """
        Crea un PaymentIntent en Stripe para la operación dada.

        La moneda se convierte a la aceptada por Stripe (PYG → USD como
        proxy de test; ajustar según necesidad real).
        El monto se pasa en centavos (entero).

        Args:
            operacion: Instancia de ``cotizaciones.Operacion``.
            currency: Código ISO de moneda para Stripe (default: 'usd').

        Returns:
            Diccionario con ``referencia`` (payment_intent_id) y
            ``client_secret`` para el frontend.
        """
        currency = kwargs.get("currency", "usd")

        # Monto en centavos (entero)
        monto_centavos = int(operacion.total_neto * 100)

        try:
            stripe = _get_stripe()
            intent = stripe.PaymentIntent.create(
                amount=monto_centavos,
                currency=currency,
                metadata={
                    "operacion_id": operacion.id,
                    "cliente": str(operacion.cliente),
                    "moneda": operacion.moneda.siglas,
                    "tipo": operacion.tipo,
                },
                description=(
                    f"Global Exchange — Operación #{operacion.id} — "
                    f"{operacion.get_tipo_display()} {operacion.monto} "
                    f"{operacion.moneda.siglas}"
                ),
            )
        except Exception as exc:
            logger.error(
                "Error creando PaymentIntent para operación %s: %s",
                operacion.id,
                exc,
                exc_info=True,
            )
            return {"exito": False, "error": str(exc)}

        # Guardar el ID del intent en la operación
        operacion.stripe_payment_intent_id = intent["id"]
        operacion.save(update_fields=["stripe_payment_intent_id"])

        logger.info(
            "PaymentIntent creado: %s para operación #%s",
            intent["id"],
            operacion.id,
        )
        return {
            "exito": True,
            "referencia": intent["id"],
            "client_secret": intent["client_secret"],
            "status": intent["status"],
        }

    def confirmar_pago(self, referencia: str, **kwargs) -> Dict[str, Any]:
        """
        Consulta el estado de un PaymentIntent en Stripe.

        Args:
            referencia: Stripe Payment Intent ID (pi_...).

        Returns:
            Diccionario con ``estado`` del intent.
        """
        try:
            stripe = _get_stripe()
            intent = stripe.PaymentIntent.retrieve(referencia)
            return {"exito": True, "estado": intent["status"], "referencia": referencia}
        except Exception as exc:
            logger.error(
                "Error consultando PaymentIntent %s: %s", referencia, exc, exc_info=True
            )
            return {"exito": False, "error": str(exc)}

    @classmethod
    def calcular_monto_stripe_usd(cls, operacion: Any) -> tuple[Decimal, int]:
        """
        Calcula el monto y centavos en USD para Stripe a partir de la operación.
        Asegura un monto mínimo válido para Stripe (~0.50 USD).

        Returns:
            Tupla (monto_usd_decimal, monto_centavos_int)
        """
        MINIMO_USD = Decimal("0.50")

        # Si la divisa de la operación ya es USD y tiene tasa > 0
        if operacion.moneda and operacion.moneda.siglas.upper() == "USD" and operacion.tasa_aplicada > 0:
            monto_usd = (operacion.total_neto / operacion.tasa_aplicada).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            # Convertir PYG a USD usando cotización de venta o tasa de referencia (7500 PYG/USD)
            from cotizaciones.models import Cotizacion
            from monedas.models import Moneda

            usd_moneda = Moneda.objects.filter(siglas__iexact="USD", activa=True).first()
            cot_usd = (
                Cotizacion.objects.filter(moneda_origen=usd_moneda, activo=True)
                .order_by("-fecha")
                .first()
                if usd_moneda
                else None
            )
            tasa_usd = cot_usd.venta if cot_usd and cot_usd.venta > 0 else Decimal("7500.00")
            monto_usd = (operacion.total_neto / tasa_usd).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        if monto_usd < MINIMO_USD:
            monto_usd = MINIMO_USD

        monto_centavos = int((monto_usd * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return monto_usd, monto_centavos

    @classmethod
    def crear_checkout_session(
        cls,
        operacion: Any,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """
        Crea una Stripe Checkout Session en modo test y retorna su URL y datos.
        """
        monto_usd, monto_centavos = cls.calcular_monto_stripe_usd(operacion)

        try:
            stripe = _get_stripe()
            session = stripe.checkout.Session.create(
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"Operación #{operacion.id} — Divisa {operacion.moneda.siglas}",
                            "description": f"Cliente: {operacion.cliente} | Liquidación: {operacion.total_neto} PYG (~{monto_usd} USD)",
                        },
                        "unit_amount": monto_centavos,
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "operacion_id": str(operacion.id),
                    "monto_centavos": str(monto_centavos),
                },
            )
        except Exception as exc:
            logger.error(
                "Error creando Checkout Session para operación %s: %s",
                operacion.id,
                exc,
                exc_info=True,
            )
            return {"exito": False, "error": str(exc)}

        # Guardar el ID de la sesión en la operación
        operacion.stripe_payment_intent_id = session.id
        operacion.save(update_fields=["stripe_payment_intent_id"])

        logger.info(
            "Checkout Session creada: %s para operación #%s (~%s USD, %s centavos)",
            session.id,
            operacion.id,
            monto_usd,
            monto_centavos,
        )
        return {
            "exito": True,
            "session_id": session.id,
            "url": session.url,
            "monto_usd": monto_usd,
            "monto_centavos": monto_centavos,
        }

    @staticmethod
    def verificar_firma_webhook(payload_raw: bytes, sig_header: str) -> Any:
        """
        Verifica la firma del webhook de Stripe usando el body crudo.

        Args:
            payload_raw: Body HTTP sin parsear (bytes).
            sig_header: Valor del header ``Stripe-Signature``.

        Returns:
            Evento Stripe deserializado si la firma es válida.

        Raises:
            stripe.error.SignatureVerificationError: Si la firma es inválida.
            RuntimeError: Si STRIPE_WEBHOOK_SECRET no está configurada.
        """
        stripe = _get_stripe()
        webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
        if not webhook_secret:
            raise RuntimeError(
                "STRIPE_WEBHOOK_SECRET no está configurada. "
                "Agregá la variable de entorno en tu .env."
            )
        return stripe.Webhook.construct_event(payload_raw, sig_header, webhook_secret)
