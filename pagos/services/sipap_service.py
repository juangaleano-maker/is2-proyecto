"""
Servicio de confirmación manual de pagos SIPAP.

Implementa la interfaz PasarelaPago para el flujo de comprobante manual:
1. El cliente adjunta un comprobante (imagen/PDF).
2. La operación queda en estado PENDIENTE_CONFIRMACION.
3. Un cajero o administrador revisa y confirma (o rechaza).
"""

import logging
from typing import Any, Dict

from django.utils import timezone

from .base import PasarelaPago

logger = logging.getLogger(__name__)


class SIPAPPasarela(PasarelaPago):
    """
    Pasarela de pago manual SIPAP.

    El flujo no implica una integración con una API externa:
    el cliente adjunta un comprobante y el cajero lo verifica manualmente.
    """

    def crear_pago(self, operacion: Any, **kwargs) -> Dict[str, Any]:
        """
        Registra la intención de pago SIPAP cambiando el estado a
        PENDIENTE_CONFIRMACION.

        Args:
            operacion: Instancia de ``cotizaciones.Operacion``.

        Returns:
            Diccionario con ``exito`` y ``referencia`` (ID de la operación).
        """
        from cotizaciones.models import Operacion

        if operacion.estado not in (
            Operacion.EstadoOperacion.PENDIENTE,
        ):
            return {
                "exito": False,
                "error": (
                    f"La operación #{operacion.id} no está en estado PENDIENTE "
                    f"(estado actual: {operacion.get_estado_display()})."
                ),
            }

        operacion.estado = Operacion.EstadoOperacion.PENDIENTE_CONFIRMACION
        operacion.save(update_fields=["estado"])

        logger.info(
            "Operación #%s movida a PENDIENTE_CONFIRMACION (SIPAP).", operacion.id
        )
        return {
            "exito": True,
            "referencia": f"SIPAP-OP-{operacion.id}",
            "estado": operacion.estado,
        }

    def confirmar_pago(self, referencia: str, **kwargs) -> Dict[str, Any]:
        """
        Confirma el pago SIPAP luego de que el cajero revisó el comprobante.

        Args:
            referencia: Referencia interna (no se usa para lookup externo).
            cajero: Usuario que confirma (keyword arg obligatorio).
            comprobante: Instancia de ``ComprobanteSIPAP`` a aprobar.

        Returns:
            Diccionario con ``exito`` y ``estado`` de la operación.
        """
        from cotizaciones.models import Operacion
        from pagos.models import ComprobanteSIPAP

        cajero = kwargs.get("cajero")
        comprobante: ComprobanteSIPAP = kwargs.get("comprobante")

        if not comprobante:
            return {"exito": False, "error": "Se requiere el comprobante para confirmar."}

        operacion = comprobante.operacion

        if operacion.estado != Operacion.EstadoOperacion.PENDIENTE_CONFIRMACION:
            return {
                "exito": False,
                "error": (
                    f"La operación no está en estado PENDIENTE_CONFIRMACION "
                    f"(estado actual: {operacion.get_estado_display()})."
                ),
            }

        # Actualizar comprobante
        comprobante.estado = ComprobanteSIPAP.EstadoComprobante.APROBADO
        comprobante.revisado_por = cajero
        comprobante.fecha_revision = timezone.now()
        comprobante.save(update_fields=["estado", "revisado_por", "fecha_revision"])

        # Actualizar operación
        operacion.estado = Operacion.EstadoOperacion.PAGADA
        operacion.save(update_fields=["estado"])

        logger.info(
            "Comprobante #%s aprobado por %s. Operación #%s → PAGADA.",
            comprobante.pk,
            cajero,
            operacion.id,
        )
        return {
            "exito": True,
            "estado": operacion.estado,
            "referencia": f"SIPAP-OP-{operacion.id}",
        }

    @staticmethod
    def rechazar_comprobante(comprobante: Any, cajero: Any, motivo: str) -> Dict[str, Any]:
        """
        Rechaza el comprobante SIPAP con un motivo registrado.

        Args:
            comprobante: Instancia de ``ComprobanteSIPAP``.
            cajero: Usuario que rechaza.
            motivo: Texto explicando el rechazo.

        Returns:
            Diccionario con ``exito`` y ``estado`` de la operación.
        """
        from cotizaciones.models import Operacion
        from pagos.models import ComprobanteSIPAP

        operacion = comprobante.operacion

        comprobante.estado = ComprobanteSIPAP.EstadoComprobante.RECHAZADO
        comprobante.revisado_por = cajero
        comprobante.fecha_revision = timezone.now()
        comprobante.motivo_rechazo = motivo
        comprobante.save(
            update_fields=["estado", "revisado_por", "fecha_revision", "motivo_rechazo"]
        )

        operacion.estado = Operacion.EstadoOperacion.RECHAZADA
        operacion.save(update_fields=["estado"])

        logger.info(
            "Comprobante #%s RECHAZADO por %s. Motivo: %s. Operación #%s → RECHAZADA.",
            comprobante.pk,
            cajero,
            motivo,
            operacion.id,
        )
        return {
            "exito": True,
            "estado": operacion.estado,
            "motivo_rechazo": motivo,
        }
