import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Cotizacion, AlertaTasa, NotificacionTasa

logger = logging.getLogger(__name__)


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
