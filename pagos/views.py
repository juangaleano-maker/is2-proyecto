"""
Vistas del módulo de pagos.

Incluye:
- webhook_stripe: Endpoint para eventos de Stripe (firma verificada).
- subir_comprobante_sipap: El cliente adjunta su comprobante.
- revisar_comprobante_sipap: Vista cajero/admin para aprobar o rechazar.
- detalle_ticket: Visualización e impresión del ticket de transacción.
- lista_comprobantes_pendientes: Lista de comprobantes en cola para el cajero.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from authentication.decorators import rol_requerido
from cotizaciones.models import Operacion

from .forms import (
    AnularFacturaForm,
    ComprobanteSIPAPForm,
    RechazarComprobanteSIPAPForm,
)
from .models import (
    ComprobanteSIPAP,
    FacturaElectronica,
    StripeEventoProcesado,
    TicketTransaccion,
)
from .services import (
    FacturaService,
    SIPAPPasarela,
    StripePasarela,
    TicketService,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Webhook Stripe
# =============================================================================

@csrf_exempt
@require_POST
def webhook_stripe(request):
    """
    Endpoint que recibe eventos de Stripe vía webhook.

    - Verifica la firma usando el body crudo (raw body).
    - Garantiza idempotencia: ignora eventos ya procesados.
    - Maneja: checkout.session.completed, payment_intent.succeeded,
      payment_intent.payment_failed.
    - Responde 200 rápido; registra errores en log.

    URL: POST /pagos/webhooks/stripe/

    Prueba local::

        stripe listen --forward-to localhost:8000/pagos/webhooks/stripe/
        stripe trigger payment_intent.succeeded
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    # --- Verificar firma ---
    try:
        evento = StripePasarela.verificar_firma_webhook(payload, sig_header)
    except Exception as exc:
        logger.warning("Firma de webhook Stripe inválida: %s", exc)
        return HttpResponse(f"Firma inválida: {exc}", status=400)

    event_id = evento.get("id", "")
    tipo_evento = evento.get("type", "")

    # --- Idempotencia ---
    if StripeEventoProcesado.objects.filter(event_id=event_id).exists():
        logger.info("Evento Stripe duplicado ignorado: %s (%s)", event_id, tipo_evento)
        return HttpResponse("ok", status=200)

    # --- Procesar evento ---
    try:
        _procesar_evento_stripe(evento)
    except Exception as exc:
        logger.error(
            "Error procesando evento Stripe %s (%s): %s",
            event_id,
            tipo_evento,
            exc,
            exc_info=True,
        )
        # Respondemos 200 para evitar que Stripe reintente indefinidamente
        return HttpResponse("ok", status=200)

    # --- Registrar como procesado ---
    StripeEventoProcesado.objects.create(
        event_id=event_id,
        tipo_evento=tipo_evento,
        datos_resumen={
            "type": tipo_evento,
            "created": evento.get("created"),
        },
    )

    return HttpResponse("ok", status=200)


def _procesar_evento_stripe(evento: dict) -> None:
    """
    Dispatcher de eventos Stripe.

    Args:
        evento: Evento Stripe deserializado por ``construct_event``.
    """
    tipo = evento.get("type", "")
    data_obj = evento.get("data", {}).get("object", {})

    if tipo in ("payment_intent.succeeded", "checkout.session.completed"):
        _handle_pago_exitoso(tipo, data_obj)
    elif tipo == "payment_intent.payment_failed":
        _handle_pago_fallido(data_obj)
    else:
        logger.debug("Evento Stripe no manejado: %s", tipo)


def _handle_pago_exitoso(tipo_evento: str, data_obj: dict) -> None:
    """
    Marca la operación como PAGADA y genera el ticket al recibir
    ``payment_intent.succeeded`` o ``checkout.session.completed``.
    """
    session_id = data_obj.get("id", "")
    payment_intent_id = (
        data_obj.get("payment_intent", "")
        if tipo_evento == "checkout.session.completed"
        else data_obj.get("id", "")
    )
    metadata = data_obj.get("metadata", {})
    metadata_op_id = metadata.get("operacion_id")

    # Localizar la operación
    operacion = None
    if metadata_op_id:
        operacion = Operacion.objects.filter(id=metadata_op_id).first()

    if not operacion and payment_intent_id:
        operacion = Operacion.objects.filter(stripe_payment_intent_id=payment_intent_id).first()

    if not operacion and session_id:
        operacion = Operacion.objects.filter(stripe_payment_intent_id=session_id).first()

    if not operacion:
        logger.warning(
            "No se encontró operación vinculada a Stripe (payment_intent=%s, session=%s, metadata_op_id=%s)",
            payment_intent_id,
            session_id,
            metadata_op_id,
        )
        return

    if operacion.estado == Operacion.EstadoOperacion.PAGADA:
        logger.info("Operación #%s ya estaba PAGADA.", operacion.id)
        return

    # Validar montos entre el evento de Stripe y la operación
    stripe_amount = data_obj.get("amount") or data_obj.get("amount_total")
    if stripe_amount is not None and metadata_op_id:
        # Si la metadata tiene el monto en centavos acordado en la sesión
        if metadata.get("monto_centavos"):
            monto_esperado = int(metadata.get("monto_centavos"))
        else:
            monto_esperado = int(operacion.total_neto * 100)

        if abs(stripe_amount - monto_esperado) > 1:
            logger.error(
                "Discrepancia de monto en Stripe (%s) vs esperado (%s) para operacion #%s",
                stripe_amount,
                monto_esperado,
                operacion.id,
            )
            return

    # Si la operación tenía guardado el session_id y ahora tenemos el payment_intent real, actualizarlo
    referencia = payment_intent_id or session_id or getattr(operacion, "stripe_payment_intent_id", "") or ""
    if payment_intent_id and operacion.stripe_payment_intent_id != payment_intent_id:
        operacion.stripe_payment_intent_id = payment_intent_id

    operacion.estado = Operacion.EstadoOperacion.PAGADA
    operacion.save(update_fields=["estado", "stripe_payment_intent_id"])

    TicketService.generar_ticket(
        operacion=operacion,
        metodo_pago=TicketTransaccion.MetodoPago.STRIPE,
        referencia_externa=referencia,
        cajero=None,
    )
    logger.info("Operación #%s → PAGADA (Stripe: %s).", operacion.id, referencia)


def _handle_pago_fallido(data_obj: dict) -> None:
    """
    Marca la operación como PAGO_FALLIDO al recibir ``payment_intent.payment_failed``.
    """
    payment_intent_id = data_obj.get("id", "")
    if not payment_intent_id:
        return

    operacion = Operacion.objects.filter(
        stripe_payment_intent_id=payment_intent_id
    ).first()

    if not operacion:
        logger.warning(
            "No se encontró operación con stripe_payment_intent_id=%s (pago fallido)",
            payment_intent_id,
        )
        return

    if operacion.estado == Operacion.EstadoOperacion.PAGO_FALLIDO:
        return

    operacion.estado = Operacion.EstadoOperacion.PAGO_FALLIDO
    operacion.save(update_fields=["estado"])
    logger.info("Operación #%s → PAGO_FALLIDO (Stripe: %s).", operacion.id, payment_intent_id)


# =============================================================================
# SIPAP — Flujo del cliente
# =============================================================================

@login_required
def subir_comprobante_sipap(request, operacion_id):
    """
    Vista para que el cliente adjunte el comprobante de pago SIPAP.

    - La operación debe estar en estado PENDIENTE.
    - Al subir exitosamente, la operación pasa a PENDIENTE_CONFIRMACION.
    - Genera el comprobante vinculado a la operación.
    """
    operacion = get_object_or_404(
        Operacion.objects.select_related("cliente", "moneda"), id=operacion_id
    )

    # Verificar que no haya comprobante previo
    if hasattr(operacion, "comprobante_sipap"):
        messages.info(
            request,
            "Ya existe un comprobante adjunto para esta operación. "
            "Esperá la revisión del cajero.",
        )
        return redirect("operacion_detalle", operacion_id=operacion.id)

    # Solo operaciones de tipo COMPRA pueden pagar/subir comprobante
    if operacion.tipo != Operacion.TipoOperacion.COMPRA:
        messages.error(
            request,
            f"El pago bancario SIPAP solo está disponible para operaciones de COMPRA de divisas (la operación #{operacion.id} es una {operacion.get_tipo_display()}).",
        )
        return redirect("operacion_detalle", operacion_id=operacion.id)

    # Solo operaciones PENDIENTE pueden subir comprobante
    if operacion.estado != Operacion.EstadoOperacion.PENDIENTE:
        messages.error(
            request,
            f"La operación #{operacion.id} no está en estado PENDIENTE "
            f"(estado: {operacion.get_estado_display()}).",
        )
        return redirect("operacion_detalle", operacion_id=operacion.id)

    if request.method == "POST":
        form = ComprobanteSIPAPForm(request.POST, request.FILES)
        if form.is_valid():
            comprobante = form.save(commit=False)
            comprobante.operacion = operacion
            comprobante.subido_por = request.user
            comprobante.save()

            # Cambiar estado vía servicio
            sipap = SIPAPPasarela()
            resultado = sipap.crear_pago(operacion)

            if resultado["exito"]:
                messages.success(
                    request,
                    "✅ Comprobante adjuntado correctamente. "
                    "La operación está pendiente de revisión por el cajero.",
                )
                return redirect("operacion_detalle", operacion_id=operacion.id)
            else:
                messages.error(request, resultado.get("error", "Error al procesar."))
        else:
            messages.error(request, "Por favor corregí los errores del formulario.")
    else:
        form = ComprobanteSIPAPForm()

    return render(
        request,
        "pagos/subir_comprobante.html",
        {"form": form, "operacion": operacion},
    )


# =============================================================================
# SIPAP — Flujo del cajero / administrador
# =============================================================================

@rol_requerido("admin", "operador", "supervisor")
def lista_comprobantes_pendientes(request):
    """
    Lista de comprobantes SIPAP en estado PENDIENTE para revisión del cajero.

    Solo accesible por cajero (operador), supervisor y administrador.
    """
    comprobantes = (
        ComprobanteSIPAP.objects.filter(estado=ComprobanteSIPAP.EstadoComprobante.PENDIENTE)
        .select_related("operacion__cliente", "operacion__moneda", "subido_por")
        .order_by("fecha_subida")
    )
    return render(
        request,
        "pagos/lista_comprobantes.html",
        {"comprobantes": comprobantes},
    )


@rol_requerido("admin", "operador", "supervisor")
def revisar_comprobante_sipap(request, comprobante_id):
    """
    Vista del cajero/administrador para revisar un comprobante SIPAP.

    - Muestra el comprobante adjunto y los detalles de la operación.
    - Botón "Confirmar pago": aprueba y genera el ticket.
    - Botón "Rechazar": pide motivo y cambia estado a RECHAZADA.
    - Registra quién confirmó/rechazó y cuándo.
    """
    comprobante = get_object_or_404(
        ComprobanteSIPAP.objects.select_related(
            "operacion__cliente", "operacion__moneda", "subido_por"
        ),
        pk=comprobante_id,
    )

    if comprobante.estado != ComprobanteSIPAP.EstadoComprobante.PENDIENTE:
        messages.info(
            request,
            f"Este comprobante ya fue {comprobante.get_estado_display().lower()}.",
        )
        return redirect("pagos:lista_comprobantes_pendientes")

    rechazo_form = RechazarComprobanteSIPAPForm()

    if request.method == "POST":
        accion = request.POST.get("accion")
        sipap = SIPAPPasarela()

        if accion == "confirmar":
            resultado = sipap.confirmar_pago(
                referencia=f"SIPAP-OP-{comprobante.operacion_id}",
                cajero=request.user,
                comprobante=comprobante,
            )
            if resultado["exito"]:
                # Generar ticket
                TicketService.generar_ticket(
                    operacion=comprobante.operacion,
                    metodo_pago=TicketTransaccion.MetodoPago.SIPAP,
                    referencia_externa=f"SIPAP-OP-{comprobante.operacion_id}",
                    cajero=request.user,
                )
                messages.success(
                    request,
                    f"✅ Pago confirmado. Ticket generado para operación "
                    f"#{comprobante.operacion_id}.",
                )
                return redirect("pagos:lista_comprobantes_pendientes")
            else:
                messages.error(request, resultado.get("error", "Error al confirmar."))

        elif accion == "rechazar":
            rechazo_form = RechazarComprobanteSIPAPForm(request.POST)
            if rechazo_form.is_valid():
                resultado = SIPAPPasarela.rechazar_comprobante(
                    comprobante=comprobante,
                    cajero=request.user,
                    motivo=rechazo_form.cleaned_data["motivo"],
                )
                messages.warning(
                    request,
                    f"❌ Comprobante rechazado. Operación "
                    f"#{comprobante.operacion_id} marcada como RECHAZADA.",
                )
                return redirect("pagos:lista_comprobantes_pendientes")
            else:
                messages.error(request, "Por favor ingresá el motivo de rechazo.")

    return render(
        request,
        "pagos/revisar_comprobante.html",
        {
            "comprobante": comprobante,
            "operacion": comprobante.operacion,
            "rechazo_form": rechazo_form,
        },
    )


# =============================================================================
# Ticket de transacción
# =============================================================================

@login_required
def detalle_ticket(request, operacion_id):
    """
    Muestra el ticket de transacción de una operación pagada.

    Accesible por el personal con rol admin/operador/supervisor
    y también por el usuario que registró la operación.
    """
    operacion = get_object_or_404(
        Operacion.objects.select_related("cliente", "moneda", "registrado_por"),
        id=operacion_id,
    )

    ticket = get_object_or_404(TicketTransaccion, operacion=operacion)

    # Control de acceso: personal o propietario de la operación
    roles = set(getattr(request, "roles", [])) | set(
        request.user.groups.values_list("name", flat=True)
    )
    roles_gestion = {"admin", "supervisor", "operador", "empleado"}
    es_personal = bool(roles.intersection(roles_gestion)) or request.user.is_staff

    if not es_personal and operacion.registrado_por != request.user:
        messages.error(request, "No tenés permiso para ver este ticket.")
        return redirect("menu")

    return render(
        request,
        "pagos/ticket_detalle.html",
        {"ticket": ticket, "operacion": operacion},
    )


# =============================================================================
# Stripe — Flujo de pago en la web
# =============================================================================

@login_required
def iniciar_pago_stripe(request, operacion_id):
    """
    Inicia el flujo de pago con Stripe en modo test.

    - GET: Muestra la pantalla de confirmación con el monto convertido a USD (mínimo 0.50 USD).
    - POST: Al presionar "Pagar con Stripe", crea la Checkout Session oficial
      (con success_url y cancel_url), guarda el ID de la sesión en la operación
      y redirige al usuario a session.url.
    - La confirmación definitiva llegará exclusivamente por el webhook firmado.
    """
    from django.conf import settings
    operacion = get_object_or_404(
        Operacion.objects.select_related("cliente", "moneda"), id=operacion_id
    )

    # Solo operaciones de tipo COMPRA pueden pagarse mediante pasarela Stripe
    if operacion.tipo != Operacion.TipoOperacion.COMPRA:
        messages.error(
            request,
            f"La pasarela de pagos Stripe solo está disponible para operaciones de COMPRA de divisas (la operación #{operacion.id} es una {operacion.get_tipo_display()}).",
        )
        return redirect("operacion_detalle", operacion_id=operacion.id)

    estados_permitidos = (
        Operacion.EstadoOperacion.PENDIENTE,
        Operacion.EstadoOperacion.PAGO_FALLIDO,
    )
    if operacion.estado not in estados_permitidos:
        messages.info(
            request,
            f"La operación #{operacion.id} ya se encuentra en estado {operacion.get_estado_display()}."
        )
        return redirect("operacion_detalle", operacion_id=operacion.id)

    monto_usd, monto_centavos = StripePasarela.calcular_monto_stripe_usd(operacion)
    stripe_key = getattr(settings, "STRIPE_SECRET_KEY", None)

    if request.method == "POST":
        # Al presionar "Pagar", crear Checkout Session oficial
        success_url = request.build_absolute_uri(
            reverse("operacion_detalle", kwargs={"operacion_id": operacion.id})
        ) + "?stripe=success"
        cancel_url = request.build_absolute_uri(
            reverse("operacion_detalle", kwargs={"operacion_id": operacion.id})
        ) + "?stripe=cancelled"

        resultado = StripePasarela.crear_checkout_session(
            operacion=operacion,
            success_url=success_url,
            cancel_url=cancel_url,
        )

        if resultado["exito"]:
            # Redirige a la pasarela alojada de Stripe
            return redirect(resultado["url"], status=303)
        else:
            messages.error(
                request,
                f"❌ Error al conectar con Stripe: {resultado.get('error')}. "
                "Verificá que STRIPE_SECRET_KEY esté configurada correctamente en tu .env."
            )

    return render(
        request,
        "pagos/checkout_stripe.html",
        {
            "operacion": operacion,
            "monto_usd": monto_usd,
            "monto_centavos": monto_centavos,
            "is_debug": settings.DEBUG,
            "stripe_configurado": bool(stripe_key and not stripe_key.startswith("sk_test_REEMPLAZAR")),
        },
    )


@login_required
@require_POST
def simular_pago_stripe(request, operacion_id):
    """
    Simulación local de webhook para desarrollo (solo si DEBUG=True).
    Dispara internamente la lógica de checkout.session.completed.
    """
    from django.conf import settings
    from django.core.exceptions import PermissionDenied

    if not settings.DEBUG:
        raise PermissionDenied("La simulación local solo está habilitada cuando DEBUG=True.")

    operacion = get_object_or_404(Operacion, id=operacion_id)
    if operacion.estado != Operacion.EstadoOperacion.PENDIENTE:
        messages.warning(
            request, f"La operación ya está en estado {operacion.get_estado_display()}."
        )
        return redirect("operacion_detalle", operacion_id=operacion.id)

    _, monto_centavos = StripePasarela.calcular_monto_stripe_usd(operacion)
    session_id = f"cs_test_sim_{operacion.id}"
    pi_id = f"pi_test_sim_{operacion.id}"
    operacion.stripe_payment_intent_id = session_id
    operacion.save(update_fields=["stripe_payment_intent_id"])

    # Disparar la lógica del webhook checkout.session.completed
    _handle_pago_exitoso(
        "checkout.session.completed",
        {
            "id": session_id,
            "payment_intent": pi_id,
            "amount_total": monto_centavos,
            "metadata": {
                "operacion_id": str(operacion.id),
                "monto_centavos": str(monto_centavos),
            },
        },
    )
    messages.success(
        request,
        f"✅ [Solo Desarrollo] Webhook checkout.session.completed simulado con éxito para operación #{operacion.id}."
    )
    return redirect("operacion_detalle", operacion_id=operacion.id)


# =============================================================================
# IS2-63: Facturación Electrónica (RF33, RF34, RNF37)
# =============================================================================

@login_required
def detalle_factura(request, factura_id):
    """
    Muestra los detalles tributarios y fiscales de la Factura Electrónica (KUDE).

    Accesible por el personal administrativo / caja y por el usuario que registró
    la operación.
    """
    factura = get_object_or_404(
        FacturaElectronica.objects.select_related(
            "operacion__cliente",
            "operacion__moneda",
            "operacion__registrado_por",
            "ticket",
            "anulada_por",
        ),
        id=factura_id,
    )

    operacion = factura.operacion
    roles = set(getattr(request, "roles", [])) | set(
        request.user.groups.values_list("name", flat=True)
    )
    roles_gestion = {"admin", "supervisor", "operador", "empleado"}
    es_personal = bool(roles.intersection(roles_gestion)) or request.user.is_staff

    if not es_personal and operacion.registrado_por != request.user:
        messages.error(request, "No tenés permiso para ver esta factura electrónica.")
        return redirect("menu")

    # Separar CDC en bloques de 4 para lectura humana
    cdc_formateado = ""
    if factura.cdc:
        cdc_formateado = " ".join(
            factura.cdc[i : i + 4] for i in range(0, len(factura.cdc), 4)
        )

    anular_form = AnularFacturaForm() if (factura.es_anulable and es_personal) else None

    return render(
        request,
        "pagos/factura_detalle.html",
        {
            "factura": factura,
            "operacion": operacion,
            "cdc_formateado": cdc_formateado,
            "es_personal": es_personal,
            "anular_form": anular_form,
        },
    )


@login_required
def detalle_factura_operacion(request, operacion_id):
    """
    Acceso directo a la Factura Electrónica a partir del ID de la Operación.
    Si la operación está PAGADA y no tenía factura aún (creada antes del módulo),
    la emite automáticamente al presionar el botón.
    """
    operacion = get_object_or_404(Operacion, id=operacion_id)

    try:
        factura = operacion.factura_electronica
        return redirect("pagos:detalle_factura", factura_id=factura.id)
    except FacturaElectronica.DoesNotExist:
        if operacion.estado == Operacion.EstadoOperacion.PAGADA:
            try:
                ticket = getattr(operacion, "ticket", None)
                factura = FacturaService.emitir_factura(operacion=operacion, ticket=ticket)
                return redirect("pagos:detalle_factura", factura_id=factura.id)
            except Exception as exc:
                logger.error(
                    "Error al generar factura para operación #%s: %s",
                    operacion.id,
                    exc,
                    exc_info=True,
                )

        messages.warning(
            request,
            f"La operación #{operacion.id} no posee aún una Factura Electrónica asociada.",
        )
        return redirect("operacion_detalle", operacion_id=operacion.id)



@login_required
@require_POST
def anular_factura_view(request, factura_id):
    """
    Endpoint para anular una Factura Electrónica en estado EMITIDA (RF34).

    Requiere rol de administración/cajero (admin, supervisor u operador)
    y motivo justificado de al menos 10 caracteres.
    """
    factura = get_object_or_404(FacturaElectronica, id=factura_id)

    roles = set(getattr(request, "roles", [])) | set(
        request.user.groups.values_list("name", flat=True)
    )
    roles_autorizados = {"admin", "supervisor", "operador"}
    if not bool(roles.intersection(roles_autorizados)) and not request.user.is_staff:
        messages.error(request, "No tenés permisos para anular facturas electrónicas.")
        return redirect("pagos:detalle_factura", factura_id=factura.id)

    form = AnularFacturaForm(request.POST)
    if not form.is_valid():
        errores = " ".join([err for sublist in form.errors.values() for err in sublist])
        messages.error(request, f"Error al anular: {errores}")
        return redirect("pagos:detalle_factura", factura_id=factura.id)

    motivo = form.cleaned_data["motivo"]
    resultado = FacturaService.anular_factura(
        factura=factura,
        usuario=request.user,
        motivo=motivo,
    )

    if resultado["exito"]:
        messages.success(
            request,
            f"✅ Factura {factura.numero_factura} anulada exitosamente.",
        )
    else:
        messages.error(request, f"❌ No se pudo anular la factura: {resultado.get('error')}")

    return redirect("pagos:detalle_factura", factura_id=factura.id)


@login_required
def kude_factura(request, factura_id):
    """
    Vista de impresión oficial en formato KUDE (Kuatia Documento Electrónico).
    Apta para imprimir directamente (Ctrl+P / Guardar como PDF).
    """
    factura = get_object_or_404(
        FacturaElectronica.objects.select_related(
            "operacion__cliente",
            "operacion__moneda",
            "operacion__registrado_por",
            "ticket",
            "anulada_por",
        ),
        id=factura_id,
    )

    operacion = factura.operacion
    roles = set(getattr(request, "roles", [])) | set(
        request.user.groups.values_list("name", flat=True)
    )
    roles_gestion = {"admin", "supervisor", "operador", "empleado"}
    es_personal = bool(roles.intersection(roles_gestion)) or request.user.is_staff

    if not es_personal and operacion.registrado_por != request.user:
        messages.error(request, "No tenés permiso para acceder a esta factura.")
        return redirect("menu")

    cdc_formateado = ""
    if factura.cdc:
        cdc_formateado = " ".join(
            factura.cdc[i : i + 4] for i in range(0, len(factura.cdc), 4)
        )

    return render(
        request,
        "pagos/factura_kude_print.html",
        {
            "factura": factura,
            "operacion": operacion,
            "cdc_formateado": cdc_formateado,
        },
    )


