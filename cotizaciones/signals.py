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

    from django.contrib.auth import get_user_model
    User = get_user_model()

    fecha_ref = instance.fecha or timezone.now()
    fecha_fmt = fecha_ref.strftime('%d/%m/%Y %H:%M')
    origen_siglas = moneda.siglas
    destino_siglas = instance.moneda_destino.siglas if instance.moneda_destino else "PYG"

    # 1. Buscar alertas activas asociadas a esta moneda
    alertas_candidatas = AlertaTasa.objects.filter(
        moneda=moneda,
        activa=True
    ).select_related('usuario', 'moneda')

    alertas_por_usuario = {}
    for alerta in alertas_candidatas:
        alertas_por_usuario.setdefault(alerta.usuario_id, []).append(alerta)

    notificaciones_a_crear = []
    usuarios_procesados = set()

    for usuario_id, alertas in alertas_por_usuario.items():
        alerta_cumplida = None
        alerta_variacion = None
        tiene_umbral = False

        for alerta in alertas:
            if alerta.tipo != AlertaTasa.TipoAlerta.VARIACION:
                tiene_umbral = True
                if alerta.se_cumple(instance):
                    alerta_cumplida = alerta
                    break
            else:
                alerta_variacion = alerta

        # Si no cumplió un umbral específico, pero tiene alerta de variación
        if not alerta_cumplida and alerta_variacion:
            alerta_cumplida = alerta_variacion

        if alerta_cumplida:
            if alerta_cumplida.tipo == AlertaTasa.TipoAlerta.VARIACION:
                titulo = f"Actualización de Tasa: {origen_siglas}"
                detalle = f"Nueva cotización de {origen_siglas} registrada."
            else:
                titulo = f"¡Alerta de Tasa Alcanzada! {origen_siglas}"
                detalle = f"La tasa alcanzó tu condición de {alerta_cumplida.get_tipo_display()} ({alerta_cumplida.valor_objetivo})."

            mensaje = (
                f"{detalle} Tasa actual a {destino_siglas}: "
                f"Compra {instance.compra} | Venta {instance.venta}. "
                f"Fecha de actualización: {fecha_fmt}."
            )

            notificaciones_a_crear.append(
                NotificacionTasa(
                    usuario_id=usuario_id,
                    moneda=moneda,
                    cotizacion=instance,
                    alerta=alerta_cumplida,
                    titulo=titulo,
                    mensaje=mensaje,
                    tasa_compra=instance.compra,
                    tasa_venta=instance.venta,
                    fecha_actualizacion=fecha_ref,
                    leida=False
                )
            )
            usuarios_procesados.add(usuario_id)
        elif tiene_umbral:
            # El usuario configuró un umbral específico (ej. compra >= X) que aún no se alcanzó.
            # No enviamos alerta hasta que se cumpla su condición configurada.
            usuarios_procesados.add(usuario_id)

    # 2. Notificar a todos los demás usuarios activos (incluyendo clientes)
    # que no fueron procesados ni tienen umbrales bloqueantes
    usuarios_restantes = User.objects.filter(is_active=True).exclude(id__in=usuarios_procesados)

    titulo_general = f"Actualización de Tasa: {origen_siglas}"
    mensaje_general = (
        f"Nueva cotización de {origen_siglas} registrada. "
        f"Tasa actual a {destino_siglas}: Compra {instance.compra} | Venta {instance.venta}. "
        f"Fecha de actualización: {fecha_fmt}."
    )

    for u in usuarios_restantes:
        notificaciones_a_crear.append(
            NotificacionTasa(
                usuario=u,
                moneda=moneda,
                cotizacion=instance,
                alerta=None,
                titulo=titulo_general,
                mensaje=mensaje_general,
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

    # Buscar sesión activa vinculada a la operación o del cajero responsable
    sesion_activa = instance.sesion_caja
    cajero = instance.registrado_por

    if not sesion_activa and cajero:
        sesion_activa = SesionCaja.objects.filter(
            cajero=cajero,
            estado=SesionCaja.EstadoSesion.ABIERTA,
        ).first()

    if not sesion_activa:
        logger.warning(
            f"[IS2-61] Operación #{instance.id} confirmada como PAGADA sin sesión de caja activa vinculada "
            f"o el usuario ({cajero.username if cajero else 'anónimo'}) no tiene caja ABIERTA actualmente."
        )
        return

    # Sincronizar caja y sesion_caja en la operación sin re-disparar post_save
    update_kwargs = {}
    if not instance.sesion_caja:
        instance.sesion_caja = sesion_activa
        update_kwargs['sesion_caja'] = sesion_activa
    if sesion_activa.caja and not instance.caja:
        instance.caja = sesion_activa.caja
        update_kwargs['caja'] = sesion_activa.caja
    if update_kwargs:
        Operacion.objects.filter(id=instance.id).update(**update_kwargs)

    # Re-verificar que no se haya creado ya el movimiento
    if MovimientoCaja.objects.filter(operacion=instance).exists():
        return

    # Determinar tipo de movimiento local (PYG) y tipo en divisa
    if instance.tipo == Operacion.TipoOperacion.COMPRA:
        tipo_local = MovimientoCaja.TipoMovimiento.INGRESO
        tipo_divisa = MovimientoCaja.TipoMovimiento.EGRESO
    else:
        tipo_local = MovimientoCaja.TipoMovimiento.EGRESO
        tipo_divisa = MovimientoCaja.TipoMovimiento.INGRESO

    monto_local = instance.subtotal
    monto_divisa = instance.monto

    moneda_str = instance.moneda.siglas if instance.moneda else ''
    concepto = (
        f"Operación #{instance.id} - {instance.get_tipo_display()} {instance.monto} {moneda_str} "
        f"(Cliente: {instance.cliente.nombre if hasattr(instance.cliente, 'nombre') else instance.cliente})"
    )

    MovimientoCaja.objects.get_or_create(
        operacion=instance,
        defaults={
            'sesion': sesion_activa,
            'tipo': tipo_local,
            'monto': monto_local,
            'moneda': instance.moneda,
            'monto_divisa': monto_divisa,
            'tipo_divisa': tipo_divisa,
            'concepto': concepto,
            'registrado_por': cajero,
        }
    )
    logger.info(
        f"[IS2-61] Movimiento de caja registrado: {tipo_local} Gs. {monto_local} | {tipo_divisa} {monto_divisa} {moneda_str} "
        f"en '{sesion_activa.nombre_caja}' para Operación #{instance.id}"
    )


# ==============================================================================
# IS2-63: Emision bajo demanda de Factura Electronica (RF33)
# ==============================================================================

@receiver(post_save, sender=Operacion)
def emitir_factura_electronica(sender, instance, created, **kwargs):
    """
    Emision bajo demanda:
    La Factura Electronica NO se genera automaticamente al confirmar el pago.
    Se emite exclusivamente cuando el usuario presiona el boton
    'Factura Electronica' en la interfaz.
    """
    return
