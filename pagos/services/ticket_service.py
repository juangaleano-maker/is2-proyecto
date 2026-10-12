"""
Servicio de generación de tickets de transacción.

El ticket es inmutable y se genera una única vez al pasar la operación
a estado PAGADA (automático vía Stripe o manual vía SIPAP).
Incluye un snapshot de los datos en el momento del pago.
"""

import logging
from typing import Any, Optional

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


class TicketService:
    """
    Genera y consulta tickets de transacción.

    Uso típico::

        ticket = TicketService.generar_ticket(
            operacion=operacion,
            metodo_pago="STRIPE",
            referencia_externa="pi_xxx",
            cajero=None,
        )
    """

    @staticmethod
    @transaction.atomic
    def generar_ticket(
        operacion: Any,
        metodo_pago: str,
        referencia_externa: str = "",
        cajero: Optional[Any] = None,
    ):
        """
        Genera el ticket de transacción para una operación pagada.

        Es idempotente: si el ticket ya existe para la operación, lo retorna
        sin crear uno nuevo (evita duplicados en reenvíos de webhook).

        Args:
            operacion: Instancia de ``cotizaciones.Operacion`` en estado PAGADA.
            metodo_pago: ``'STRIPE'`` o ``'SIPAP'``.
            referencia_externa: ID externo (Stripe PI ID o referencia SIPAP).
            cajero: Usuario cajero que confirmó (solo flujo manual).

        Returns:
            Instancia de ``TicketTransaccion``.

        Raises:
            ValueError: Si la operación no está en estado PAGADA.
        """
        from cotizaciones.models import Operacion
        from pagos.models import TicketTransaccion

        if operacion.estado != Operacion.EstadoOperacion.PAGADA:
            raise ValueError(
                f"Solo se puede generar ticket para operaciones PAGADAS. "
                f"Estado actual: {operacion.get_estado_display()}."
            )

        # Idempotencia: retornar ticket existente si ya fue generado
        try:
            ticket_existente = operacion.ticket
            logger.info(
                "Ticket %s ya existía para operación #%s. Retornando el existente.",
                ticket_existente.numero_ticket,
                operacion.id,
            )
            return ticket_existente
        except TicketTransaccion.DoesNotExist:
            pass

        # Snapshot de datos del cliente en el momento del pago
        cliente = operacion.cliente
        if cliente.tipo_persona == "FISICA":
            cliente_nombre = f"{cliente.nombre} {cliente.apellido}".strip()
        else:
            cliente_nombre = cliente.razon_social or str(cliente)

        try:
            ticket = TicketTransaccion.objects.create(
                operacion=operacion,
                cliente_nombre=cliente_nombre,
                cliente_documento=cliente.documento,
                monto=operacion.monto,
                moneda_siglas=operacion.moneda.siglas,
                tasa_aplicada=operacion.tasa_aplicada,
                comision=operacion.comision,
                total_neto=operacion.total_neto,
                metodo_pago=metodo_pago,
                referencia_externa=referencia_externa or "",
                cajero=cajero,
            )
        except IntegrityError:
            # Race condition: otro proceso ya creó el ticket
            ticket = operacion.ticket
            logger.warning(
                "Race condition al crear ticket para operación #%s. Retornando existente.",
                operacion.id,
            )

        logger.info(
            "Ticket %s generado para operación #%s (%s).",
            ticket.numero_ticket,
            operacion.id,
            metodo_pago,
        )
        return ticket

    @staticmethod
    def obtener_ticket(operacion_id: int):
        """
        Obtiene el ticket de una operación por su ID.

        Args:
            operacion_id: ID de la operación.

        Returns:
            ``TicketTransaccion`` o ``None`` si no existe.
        """
        from pagos.models import TicketTransaccion

        return TicketTransaccion.objects.filter(operacion_id=operacion_id).first()
