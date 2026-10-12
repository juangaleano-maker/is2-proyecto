import logging
from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Cotizacion,
    AlertaTasa,
    NotificacionTasa,
    Operacion,
    SesionCaja,
    MovimientoCaja,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# IS2-58: Notificación por variación de tasa
# ==============================================================================

@receiver(post_save, sender=Cotizacion)
def notificar_variacion_tasa(sender, instance, created, **kwargs):
    """
    Criterios de Aceptación IS2-58:
    1. Cuando un administrador o el sistema actualice la cotización de una moneda,
       se debe verificar si cumple con la condición de alguna alerta configurada.
    2. Si se cumple la condición, el sistema debe enviar una notificación al usuario.
    3. La notificación debe indicar claramente la moneda, la nueva tasa y la fecha de actualización.
    """
    # Solo procesamos si la cotización está activa (vigente)
    if not instance.activo:
        return

    # Moneda origen de la cotización
    moneda = instance.moneda_origen
    if not moneda:
        return

    # Buscar alertas activas asociadas a esta moneda
    alertas_candidatas = AlertaTasa.objects.filter(
        moneda=moneda,
        activa=True
    ).select_related('usuario', 'moneda')

    if not alertas_candidatas.exists():
        return

    fecha_ref = instance.fecha or timezone.now()
    fecha_fmt = fecha_ref.strftime('%d/%m/%Y %H:%M')
    origen_siglas = moneda.siglas
    destino_siglas = instance.moneda_destino.siglas if instance.moneda_destino else "PYG"

    notificaciones_a_crear = []
    for alerta in alertas_candidatas:
        if alerta.se_cumple(instance):
            if alerta.tipo == AlertaTasa.TipoAlerta.VARIACION:
                titulo = f"Actualización de Tasa: {origen_siglas}"
                detalle = f"Nueva cotización de {origen_siglas} registrada."
            else:
                titulo = f"¡Alerta de Tasa Alcanzada! {origen_siglas}"
                detalle = f"La tasa alcanzó tu condición de {alerta.get_tipo_display()} ({alerta.valor_objetivo})."

            mensaje = (
                f"{detalle} Tasa actual a {destino_siglas}: "
                f"Compra {instance.compra} | Venta {instance.venta}. "
                f"Fecha de actualización: {fecha_fmt}."
            )

            notificaciones_a_crear.append(
                NotificacionTasa(
                    usuario=alerta.usuario,
                    moneda=moneda,
                    cotizacion=instance,
                    alerta=alerta,
                    titulo=titulo,
                    mensaje=mensaje,
                    tasa_compra=instance.compra,
                    tasa_venta=instance.venta,
                    fecha_actualizacion=fecha_ref,
                    leida=False
                )
            )

    if notificaciones_a_crear:
        NotificacionTasa.objects.bulk_create(notificaciones_a_crear)
        logger.info(
            "Se generaron %d notificaciones de variación de tasa para cotización #%s (%s)",
            len(notificaciones_a_crear),
            instance.id,
            origen_siglas
        )


# ==============================================================================
# IS2-61: Registro automático de movimiento de caja en operación PAGADA
# ==============================================================================

@receiver(post_save, sender=Operacion)
def registrar_movimiento_caja_operacion(sender, instance, created, **kwargs):
    """
    Cada vez que una Operacion pasa al estado PAGADA, registra automáticamente
    un MovimientoCaja en la sesión de caja activa del cajero responsable (IS2-61).
    - COMPRA: el cliente entrega divisas y la casa entrega guaraníes (o viceversa según modelo de negocio).
      En el sistema actual, COMPRA = ingreso al arqueo de caja local (subtotal).
      VENTA = egreso de fondos de caja local (subtotal).
    - Evita duplicados: si ya existe un movimiento asociado a la operación, no lo recrea.
    """
    if instance.estado != Operacion.EstadoOperacion.PAGADA:
        return

    # Evitar duplicados si ya tiene movimiento creado
    if hasattr(instance, 'movimiento_caja') and instance.movimiento_caja is not None:
        return
    if MovimientoCaja.objects.filter(operacion=instance).exists():
        return

    # Buscar sesión activa del cajero responsable
    cajero = instance.registrado_por
    if not cajero:
        logger.warning(
            f"[IS2-61] Operación #{instance.id} confirmada como PAGADA sin usuario registrado_por. "
            f"No se pudo vincular a ninguna caja."
        )
        return

    sesion_activa = SesionCaja.objects.filter(
        cajero=cajero,
        estado=SesionCaja.EstadoSesion.ABIERTA,
    ).first()

    if not sesion_activa:
        logger.warning(
            f"[IS2-61] Operación #{instance.id} pagada por {cajero.username}, "
            f"pero el usuario NO tiene una sesión de caja ABIERTA actualmente."
        )
        return

    # Determinar tipo de movimiento y monto
    tipo = (
        MovimientoCaja.TipoMovimiento.INGRESO
        if instance.tipo == Operacion.TipoOperacion.COMPRA
        else MovimientoCaja.TipoMovimiento.EGRESO
    )
    monto = instance.subtotal

    moneda_str = instance.moneda.siglas if instance.moneda else ''
    concepto = (
        f"Operación #{instance.id} - {instance.get_tipo_display()} {instance.monto} {moneda_str} "
        f"(Cliente: {instance.cliente.nombre if hasattr(instance.cliente, 'nombre') else instance.cliente})"
    )

    MovimientoCaja.objects.create(
        sesion=sesion_activa,
        tipo=tipo,
        monto=monto,
        concepto=concepto,
        operacion=instance,
        registrado_por=cajero,
    )
    logger.info(
        f"[IS2-61] Movimiento de caja registrado: {tipo} Gs. {monto} en '{sesion_activa.nombre_caja}' "
        f"para Operación #{instance.id}"
    )
