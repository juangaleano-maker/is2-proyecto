import logging
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Operacion, SesionCaja, MovimientoCaja

logger = logging.getLogger(__name__)


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
    # En cotizaciones: COMPRA suma a los ingresos del cajero, VENTA a los egresos
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
