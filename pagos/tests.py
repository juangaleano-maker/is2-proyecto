"""
Pruebas del módulo de pagos (IS2-55).

Cubre:
1. Webhook Stripe:
   - Firma válida e inválida (400)
   - checkout.session.completed y payment_intent.succeeded (transición a PAGADA + Ticket)
   - payment_intent.payment_failed (transición a PAGO_FALLIDO)
   - Idempotencia (mismo evento procesado 2 veces)
   - Doble confirmación / validación de montos
2. Confirmación manual SIPAP:
   - Subida de comprobante por el cliente (JPG/PNG/PDF, max 5MB)
   - Transición de PENDIENTE a PENDIENTE_CONFIRMACION
   - Revisión por cajero/admin (Aprobación y Rechazo con motivo)
   - Registro de auditoría (quién confirmó y cuándo)
   - Restricción de permisos (rol cajero/admin vs cliente sin permiso)
3. Ticket de transacción:
   - Inmutabilidad y unicidad de número de ticket
   - Snapshot de datos financieros y de cliente
   - Control de acceso a la vista de detalle del ticket
"""

from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from clientes.models import Cliente
from cotizaciones.models import Operacion
from monedas.models import Moneda
from pagos.models import (
    ComprobanteSIPAP,
    FacturaElectronica,
    StripeEventoProcesado,
    TicketTransaccion,
)
from pagos.services import (
    FacturaService,
    SIPAPPasarela,
    StripePasarela,
    TicketService,
)

User = get_user_model()


class BasePagosTestCase(TestCase):
    """Setup base común para pruebas del módulo de pagos."""

    def setUp(self):
        # Grupos de usuarios
        self.grupo_admin = Group.objects.create(name="admin")
        self.grupo_operador = Group.objects.create(name="operador")
        self.grupo_cliente = Group.objects.create(name="cliente")

        # Usuarios
        self.user_admin = User.objects.create_user(
            username="admin_user", email="admin@exchange.com", password="password123"
        )
        self.user_admin.groups.add(self.grupo_admin)

        self.user_cajero = User.objects.create_user(
            username="cajero_juan", email="cajero@exchange.com", password="password123"
        )
        self.user_cajero.groups.add(self.grupo_operador)

        self.user_cliente = User.objects.create_user(
            username="cliente_maria", email="maria@exchange.com", password="password123"
        )
        self.user_cliente.groups.add(self.grupo_cliente)

        self.user_ajeno = User.objects.create_user(
            username="usuario_ajeno", email="ajeno@exchange.com", password="password123"
        )
        self.user_ajeno.groups.add(self.grupo_cliente)

        # Moneda
        self.usd = Moneda.objects.create(nombre="Dólar Estadounidense", siglas="USD", activa=True)

        # Cliente de negocio
        self.cliente_entidad = Cliente.objects.create(
            nombre="María",
            apellido="López",
            documento="4567890",
            email="maria@exchange.com",
            telefono="0981123456",
            tipo_persona=Cliente.TipoPersona.FISICA,
            segmento=Cliente.Segmento.MINORISTA,
            activo=True,
        )

        # Operación en estado PENDIENTE (COMPRA de divisas)
        self.operacion = Operacion.objects.create(
            cliente=self.cliente_entidad,
            moneda=self.usd,
            monto=Decimal("100.00"),
            tasa_aplicada=Decimal("7500.00"),
            tipo=Operacion.TipoOperacion.COMPRA,
            estado=Operacion.EstadoOperacion.PENDIENTE,
            registrado_por=self.user_cliente,
            comision=Decimal("15000.00"),
        )
        # total_neto = subtotal (750.000) + comision (15.000) = 765.000


class StripeWebhookTests(BasePagosTestCase):
    """Pruebas del webhook de Stripe (verificación de firma, idempotencia, estados)."""

    def setUp(self):
        super().setUp()
        self.webhook_url = reverse("pagos:webhook_stripe")
        self.operacion.stripe_payment_intent_id = "pi_test_abc123"
        self.operacion.save()

    def test_webhook_firma_invalida_retorna_400(self):
        """Si la firma de Stripe no es válida, debe responder HTTP 400."""
        with patch.object(
            StripePasarela,
            "verificar_firma_webhook",
            side_effect=Exception("Firma inválida"),
        ):
            response = self.client.post(
                self.webhook_url,
                data=b'{"id": "evt_123"}',
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig_invalida",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("Firma", response.content.decode())

    def test_webhook_payment_intent_succeeded_marca_pagada_y_genera_ticket(self):
        """payment_intent.succeeded pasa la operación a PAGADA y crea el ticket."""
        mock_evento = {
            "id": "evt_test_succ_01",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_abc123",
                    "amount": int(self.operacion.total_neto * 100),
                    "metadata": {"operacion_id": self.operacion.id},
                }
            },
        }

        with patch.object(StripePasarela, "verificar_firma_webhook", return_value=mock_evento):
            response = self.client.post(
                self.webhook_url,
                data=json.dumps(mock_evento).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig_valida",
            )
            self.assertEqual(response.status_code, 200)

        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PAGADA)

        # Ticket generado
        ticket = TicketTransaccion.objects.filter(operacion=self.operacion).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.metodo_pago, TicketTransaccion.MetodoPago.STRIPE)
        self.assertEqual(ticket.referencia_externa, "pi_test_abc123")
        self.assertEqual(ticket.total_neto, self.operacion.total_neto)

    def test_webhook_checkout_session_completed_marca_pagada(self):
        """checkout.session.completed también pasa la operación a PAGADA."""
        mock_evento = {
            "id": "evt_test_checkout_01",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_999",
                    "payment_intent": "pi_test_abc123",
                    "amount_total": int(self.operacion.total_neto * 100),
                    "metadata": {"operacion_id": self.operacion.id},
                }
            },
        }

        with patch.object(StripePasarela, "verificar_firma_webhook", return_value=mock_evento):
            response = self.client.post(
                self.webhook_url,
                data=json.dumps(mock_evento).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig_valida",
            )
            self.assertEqual(response.status_code, 200)

        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PAGADA)
        self.assertTrue(TicketTransaccion.objects.filter(operacion=self.operacion).exists())

    def test_webhook_payment_intent_failed_marca_operacion_fallida(self):
        """payment_intent.payment_failed pasa la operación a PAGO_FALLIDO."""
        mock_evento = {
            "id": "evt_test_failed_01",
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "pi_test_abc123",
                }
            },
        }

        with patch.object(StripePasarela, "verificar_firma_webhook", return_value=mock_evento):
            response = self.client.post(
                self.webhook_url,
                data=json.dumps(mock_evento).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig_valida",
            )
            self.assertEqual(response.status_code, 200)

        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PAGO_FALLIDO)
        self.assertFalse(TicketTransaccion.objects.filter(operacion=self.operacion).exists())

    def test_webhook_idempotencia_evento_duplicado_no_repite_efectos(self):
        """Si Stripe reenvía el mismo evento, se responde 200 y no se duplica el ticket."""
        mock_evento = {
            "id": "evt_test_duplicado_01",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_abc123",
                    "amount": int(self.operacion.total_neto * 100),
                    "metadata": {"operacion_id": self.operacion.id},
                }
            },
        }

        with patch.object(StripePasarela, "verificar_firma_webhook", return_value=mock_evento):
            # Primer intento
            res1 = self.client.post(
                self.webhook_url,
                data=json.dumps(mock_evento).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig_valida",
            )
            self.assertEqual(res1.status_code, 200)

            # Segundo intento (duplicado)
            res2 = self.client.post(
                self.webhook_url,
                data=json.dumps(mock_evento).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig_valida",
            )
            self.assertEqual(res2.status_code, 200)

        # Solo existe 1 ticket y 1 registro de evento procesado
        self.assertEqual(TicketTransaccion.objects.filter(operacion=self.operacion).count(), 1)
        self.assertEqual(
            StripeEventoProcesado.objects.filter(event_id="evt_test_duplicado_01").count(), 1
        )

    def test_webhook_discrepancia_monto_no_marca_pagada(self):
        """Si el monto de Stripe difiere del esperado en la orden, no se da por pagada."""
        mock_evento = {
            "id": "evt_test_bad_amount",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_abc123",
                    "amount": 999,  # Monto incorrecto
                    "metadata": {"operacion_id": self.operacion.id},
                }
            },
        }

        with patch.object(StripePasarela, "verificar_firma_webhook", return_value=mock_evento):
            response = self.client.post(
                self.webhook_url,
                data=json.dumps(mock_evento).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig_valida",
            )
            self.assertEqual(response.status_code, 200)

        self.operacion.refresh_from_db()
        # No debe haber cambiado a PAGADA por la discrepancia
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PENDIENTE)


class SIPAPFlujoTests(BasePagosTestCase):
    """Pruebas del flujo SIPAP: cliente adjunta comprobante y cajero revisa."""

    def test_cliente_sube_comprobante_valido_pasa_a_pendiente_confirmacion(self):
        """El cliente adjunta una imagen JPG válida y la operación pasa a PENDIENTE_CONFIRMACION."""
        self.client.force_login(self.user_cliente)

        archivo = SimpleUploadedFile(
            "transferencia.jpg",
            b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100,
            content_type="image/jpeg",
        )

        url = reverse("pagos:subir_comprobante_sipap", kwargs={"operacion_id": self.operacion.id})
        response = self.client.post(url, {"archivo": archivo})

        self.assertRedirects(
            response,
            reverse("operacion_detalle", kwargs={"operacion_id": self.operacion.id}),
        )

        self.operacion.refresh_from_db()
        self.assertEqual(
            self.operacion.estado, Operacion.EstadoOperacion.PENDIENTE_CONFIRMACION
        )

        # Comprobante creado
        comprobante = ComprobanteSIPAP.objects.filter(operacion=self.operacion).first()
        self.assertIsNotNone(comprobante)
        self.assertEqual(comprobante.estado, ComprobanteSIPAP.EstadoComprobante.PENDIENTE)
        self.assertEqual(comprobante.subido_por, self.user_cliente)

    def test_subir_comprobante_extension_invalida_rechazado(self):
        """Un archivo con extensión .exe no es permitido."""
        self.client.force_login(self.user_cliente)

        archivo = SimpleUploadedFile("malware.exe", b"MZ...", content_type="application/octet-stream")
        url = reverse("pagos:subir_comprobante_sipap", kwargs={"operacion_id": self.operacion.id})
        response = self.client.post(url, {"archivo": archivo})

        self.assertEqual(response.status_code, 200)  # Renderiza de nuevo con error de form
        self.assertFalse(ComprobanteSIPAP.objects.filter(operacion=self.operacion).exists())

    def test_cajero_aprueba_comprobante_marca_pagada_y_genera_ticket(self):
        """El cajero aprueba el comprobante: pasa a PAGADA y genera ticket con cajero registrado."""
        # Pre-crear comprobante
        self.operacion.estado = Operacion.EstadoOperacion.PENDIENTE_CONFIRMACION
        self.operacion.save()

        archivo = SimpleUploadedFile("comprobante.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        comprobante = ComprobanteSIPAP.objects.create(
            operacion=self.operacion,
            archivo=archivo,
            subido_por=self.user_cliente,
        )

        # Iniciar sesión como cajero (operador)
        self.client.force_login(self.user_cajero)

        url = reverse(
            "pagos:revisar_comprobante_sipap", kwargs={"comprobante_id": comprobante.id}
        )
        response = self.client.post(url, {"accion": "confirmar"})

        self.assertRedirects(response, reverse("pagos:lista_comprobantes_pendientes"))

        comprobante.refresh_from_db()
        self.operacion.refresh_from_db()

        self.assertEqual(comprobante.estado, ComprobanteSIPAP.EstadoComprobante.APROBADO)
        self.assertEqual(comprobante.revisado_por, self.user_cajero)
        self.assertIsNotNone(comprobante.fecha_revision)

        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PAGADA)

        # Ticket generado con auditoría de cajero
        ticket = TicketTransaccion.objects.get(operacion=self.operacion)
        self.assertEqual(ticket.metodo_pago, TicketTransaccion.MetodoPago.SIPAP)
        self.assertEqual(ticket.cajero, self.user_cajero)

    def test_cajero_rechaza_comprobante_con_motivo_marca_rechazada(self):
        """El cajero rechaza el comprobante ingresando motivo: la operación pasa a RECHAZADA."""
        self.operacion.estado = Operacion.EstadoOperacion.PENDIENTE_CONFIRMACION
        self.operacion.save()

        archivo = SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4...", content_type="application/pdf")
        comprobante = ComprobanteSIPAP.objects.create(
            operacion=self.operacion,
            archivo=archivo,
            subido_por=self.user_cliente,
        )

        self.client.force_login(self.user_cajero)

        url = reverse(
            "pagos:revisar_comprobante_sipap", kwargs={"comprobante_id": comprobante.id}
        )
        motivo_test = "El comprobante no tiene número de transferencia visible ni sello bancario."
        response = self.client.post(url, {"accion": "rechazar", "motivo": motivo_test})

        self.assertRedirects(response, reverse("pagos:lista_comprobantes_pendientes"))

        comprobante.refresh_from_db()
        self.operacion.refresh_from_db()

        self.assertEqual(comprobante.estado, ComprobanteSIPAP.EstadoComprobante.RECHAZADO)
        self.assertEqual(comprobante.motivo_rechazo, motivo_test)
        self.assertEqual(comprobante.revisado_por, self.user_cajero)
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.RECHAZADA)

    def test_usuario_sin_rol_cajero_es_bloqueado_en_revision_sipap(self):
        """Un usuario normal con rol 'cliente' no puede acceder a la revisión de comprobantes."""
        self.client.force_login(self.user_cliente)

        url = reverse("pagos:lista_comprobantes_pendientes")
        response = self.client.get(url)
        # @rol_requerido levanta PermissionDenied (403)
        self.assertEqual(response.status_code, 403)

    def test_doble_confirmacion_comprobante_ya_revisado_es_prevenida(self):
        """Un comprobante que ya fue aprobado no permite volver a ser confirmado."""
        self.operacion.estado = Operacion.EstadoOperacion.PAGADA
        self.operacion.save()

        archivo = SimpleUploadedFile("comprobante.jpg", b"fake", content_type="image/jpeg")
        comprobante = ComprobanteSIPAP.objects.create(
            operacion=self.operacion,
            archivo=archivo,
            estado=ComprobanteSIPAP.EstadoComprobante.APROBADO,
            revisado_por=self.user_cajero,
        )

        self.client.force_login(self.user_cajero)
        url = reverse(
            "pagos:revisar_comprobante_sipap", kwargs={"comprobante_id": comprobante.id}
        )
        response = self.client.get(url)
        self.assertRedirects(response, reverse("pagos:lista_comprobantes_pendientes"))


class TicketTransaccionTests(BasePagosTestCase):
    """Pruebas del servicio y modelo TicketTransaccion (inmutabilidad, unicidad, visualización)."""

    def setUp(self):
        super().setUp()
        self.operacion.estado = Operacion.EstadoOperacion.PAGADA
        self.operacion.save()

    def test_generar_ticket_exitoso_y_numero_con_prefijo_tkt(self):
        """Genera un ticket con prefijo TKT- y snapshot de datos financieros."""
        ticket = TicketService.generar_ticket(
            operacion=self.operacion,
            metodo_pago=TicketTransaccion.MetodoPago.STRIPE,
            referencia_externa="pi_test_xyz",
        )
        self.assertTrue(ticket.numero_ticket.startswith("TKT-"))
        self.assertEqual(ticket.monto, self.operacion.monto)
        self.assertEqual(ticket.moneda_siglas, "USD")
        self.assertEqual(ticket.tasa_aplicada, self.operacion.tasa_aplicada)
        self.assertEqual(ticket.total_neto, self.operacion.total_neto)
        self.assertEqual(ticket.cliente_documento, self.cliente_entidad.documento)

    def test_generar_ticket_operacion_no_pagada_levanta_error(self):
        """Intentar generar ticket para una operación que no está PAGADA levanta ValueError."""
        self.operacion.estado = Operacion.EstadoOperacion.PENDIENTE
        self.operacion.save()

        with self.assertRaises(ValueError):
            TicketService.generar_ticket(
                operacion=self.operacion,
                metodo_pago=TicketTransaccion.MetodoPago.STRIPE,
            )

    def test_generar_ticket_idempotente_retorna_mismo_ticket(self):
        """Llamar a generar_ticket 2 veces retorna la misma instancia sin error."""
        ticket1 = TicketService.generar_ticket(
            operacion=self.operacion,
            metodo_pago=TicketTransaccion.MetodoPago.STRIPE,
            referencia_externa="pi_1",
        )
        ticket2 = TicketService.generar_ticket(
            operacion=self.operacion,
            metodo_pago=TicketTransaccion.MetodoPago.STRIPE,
            referencia_externa="pi_1",
        )
        self.assertEqual(ticket1.pk, ticket2.pk)
        self.assertEqual(ticket1.numero_ticket, ticket2.numero_ticket)

    def test_detalle_ticket_accesible_por_cliente_propietario(self):
        """El cliente que registró la operación puede ver su ticket."""
        TicketService.generar_ticket(
            operacion=self.operacion,
            metodo_pago=TicketTransaccion.MetodoPago.STRIPE,
            referencia_externa="pi_owner",
        )

        self.client.force_login(self.user_cliente)
        url = reverse("pagos:detalle_ticket", kwargs={"operacion_id": self.operacion.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAGO CONFIRMADO")
        self.assertContains(response, self.operacion.ticket.numero_ticket)

    def test_detalle_ticket_bloquea_usuario_ajeno(self):
        """Un usuario ajeno (sin rol de gestión y no propietario) no puede ver el ticket."""
        TicketService.generar_ticket(
            operacion=self.operacion,
            metodo_pago=TicketTransaccion.MetodoPago.STRIPE,
            referencia_externa="pi_private",
        )

        self.client.force_login(self.user_ajeno)
        url = reverse("pagos:detalle_ticket", kwargs={"operacion_id": self.operacion.id})
        response = self.client.get(url)

        self.assertRedirects(response, reverse("menu"))


class StripeCheckoutWebTests(BasePagosTestCase):
    """Pruebas del flujo web de Stripe Checkout y control de simulación por DEBUG."""

    def setUp(self):
        super().setUp()
        self.iniciar_url = reverse(
            "pagos:iniciar_pago_stripe", kwargs={"operacion_id": self.operacion.id}
        )
        self.simular_url = reverse(
            "pagos:simular_pago_stripe", kwargs={"operacion_id": self.operacion.id}
        )
        self.client.force_login(self.user_cliente)

    def test_calcular_monto_stripe_usd_respeta_minimo_y_conversion(self):
        """Verifica que el cálculo en USD respete el mínimo de 0.50 USD."""
        # 1. Operación normal: 765.000 PYG con tasa 7.500 PYG/USD = 102.00 USD
        monto_usd, centavos = StripePasarela.calcular_monto_stripe_usd(self.operacion)
        self.assertEqual(monto_usd, Decimal("102.00"))
        self.assertEqual(centavos, 10200)

        # 2. Operación mínima: forzar monto diminuto
        self.operacion.monto = Decimal("0.01")  # 0.01 * 7500 = 75 PYG
        self.operacion.comision = Decimal("0.00")
        self.operacion.save()
        monto_usd_min, centavos_min = StripePasarela.calcular_monto_stripe_usd(self.operacion)
        self.assertEqual(monto_usd_min, Decimal("0.50"))
        self.assertEqual(centavos_min, 50)

    def test_iniciar_pago_stripe_get_muestra_pantalla_con_monto_usd(self):
        """GET a /pagos/stripe/<id>/iniciar/ muestra el monto USD y botón para Stripe Checkout."""
        response = self.client.get(self.iniciar_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pagos/checkout_stripe.html")
        self.assertContains(response, "Pagar con Stripe")
        self.assertContains(response, "$102.00 USD")

    def test_iniciar_pago_stripe_post_crea_checkout_session_y_redirige(self):
        """POST a /pagos/stripe/<id>/iniciar/ crea Checkout Session y redirige a session.url."""
        mock_resultado = {
            "exito": True,
            "session_id": "cs_test_mock_12345",
            "url": "https://checkout.stripe.com/c/pay/cs_test_mock_12345",
            "monto_usd": Decimal("102.00"),
            "monto_centavos": 10200,
        }

        with patch.object(
            StripePasarela, "crear_checkout_session", return_value=mock_resultado
        ) as mock_create:
            response = self.client.post(self.iniciar_url)

            # Verifica redirección a la URL de Stripe
            self.assertIn(response.status_code, [302, 303])
            self.assertEqual(response["Location"], "https://checkout.stripe.com/c/pay/cs_test_mock_12345")
            self.assertTrue(mock_create.called)

        self.operacion.refresh_from_db()
        # La operación sigue PENDIENTE: la confirmación debe llegar solo por el webhook firmado
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PENDIENTE)

    def test_simular_pago_stripe_con_debug_true_procesa_webhook(self):
        """Con DEBUG=True, el endpoint de simulación procesa el webhook y marca PAGADA."""
        with self.settings(DEBUG=True):
            response = self.client.post(self.simular_url)
            self.assertRedirects(
                response,
                reverse("operacion_detalle", kwargs={"operacion_id": self.operacion.id}),
            )

        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PAGADA)
        self.assertTrue(TicketTransaccion.objects.filter(operacion=self.operacion).exists())

    def test_simular_pago_stripe_con_debug_false_es_prohibido(self):
        """Con DEBUG=False, el endpoint de simulación responde 403 Forbidden."""
        with self.settings(DEBUG=False):
            response = self.client.post(self.simular_url)
            self.assertEqual(response.status_code, 403)

        self.operacion.refresh_from_db()
        # No debe haber cambiado de estado
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PENDIENTE)

    def test_iniciar_pago_stripe_rechaza_operacion_tipo_venta(self):
        """Operación de tipo VENTA no puede ser pagada por pasarela Stripe."""
        self.operacion.tipo = Operacion.TipoOperacion.VENTA
        self.operacion.save(update_fields=["tipo"])
        response = self.client.get(self.iniciar_url)
        self.assertRedirects(
            response,
            reverse("operacion_detalle", kwargs={"operacion_id": self.operacion.id}),
        )

    def test_subir_comprobante_sipap_rechaza_operacion_tipo_venta(self):
        """Operación de tipo VENTA no puede adjuntar comprobante SIPAP."""
        self.operacion.tipo = Operacion.TipoOperacion.VENTA
        self.operacion.save(update_fields=["tipo"])
        url = reverse("pagos:subir_comprobante_sipap", kwargs={"operacion_id": self.operacion.id})
        response = self.client.get(url)
        self.assertRedirects(
            response,
            reverse("operacion_detalle", kwargs={"operacion_id": self.operacion.id}),
        )





# ==============================================================================
# IS2-63: Pruebas de Facturación Electrónica (RF33, RF34, RNF37)
# ==============================================================================

class FacturaElectronicaTestCase(BasePagosTestCase):
    """
    Pruebas para el módulo de Facturación Electrónica (IS2-63).

    Criterios cubiertos:
    - RF33: Generación e integración asociada a transacción confirmada (PAGADA).
    - RF34: Gestión del estado (EMITIDA -> ANULADA, rechazo de anulación en estados inválidos).
    - RNF37: Desempeño del simulador (completar en <= 5 segundos).
    - Idempotencia del servicio.
    - Fórmula fiscal SIFEN (Base imponible 10%, IVA 10%, Total).
    """

    def setUp(self):
        super().setUp()
        self.operacion.estado = Operacion.EstadoOperacion.PAGADA
        self.operacion.save()

    def test_emision_factura_operacion_pagada(self):
        """Al emitir factura para una operación PAGADA se genera FacturaElectronica con CDC de 44 dígitos."""
        factura = FacturaService.emitir_factura(self.operacion)
        self.assertEqual(factura.estado, FacturaElectronica.EstadoFactura.EMITIDA)
        self.assertTrue(factura.numero_factura.startswith("001-003-"))
        self.assertIsNotNone(factura.cdc)
        self.assertEqual(len(factura.cdc), 44)
        self.assertEqual(factura.cliente_nombre, "María López")
        self.assertEqual(factura.cliente_documento, "4567890")
        self.assertEqual(factura.moneda_siglas, "USD")

    def test_idempotencia_emision_factura(self):
        """Emitir_factura múltiples veces retorna la misma factura sin duplicados."""
        factura_1 = FacturaService.emitir_factura(self.operacion)
        factura_2 = FacturaService.emitir_factura(self.operacion)

        self.assertEqual(factura_1.id, factura_2.id)
        self.assertEqual(factura_1.numero_factura, factura_2.numero_factura)
        self.assertEqual(FacturaElectronica.objects.filter(operacion=self.operacion).count(), 1)

    def test_calculo_desglose_iva_sifen(self):
        """Verifica que el desglose tributario cumpla con la fórmula oficial SIFEN."""
        subtotal = self.operacion.subtotal
        self.assertEqual(subtotal, Decimal("750000.00"))

        base, iva, total = FacturaService._calcular_desglose_iva(subtotal)

        self.assertEqual(base, Decimal("681818.18"))
        self.assertEqual(iva, Decimal("68181.82"))
        self.assertEqual(total, Decimal("750000.00"))
        self.assertEqual(base + iva, total)

    def test_anular_factura_servicio_exitoso(self):
        """FacturaService.anular_factura cambia estado a ANULADA y registra auditoría."""
        factura = FacturaService.emitir_factura(self.operacion)
        self.assertTrue(factura.es_anulable)

        motivo = "Error en los datos de facturación del cliente"
        resultado = FacturaService.anular_factura(
            factura=factura,
            usuario=self.user_cajero,
            motivo=motivo,
        )

        self.assertTrue(resultado["exito"])
        factura.refresh_from_db()
        self.assertEqual(factura.estado, FacturaElectronica.EstadoFactura.ANULADA)
        self.assertEqual(factura.anulada_por, self.user_cajero)
        self.assertEqual(factura.motivo_anulacion, motivo)
        self.assertIsNotNone(factura.fecha_procesado)
        self.assertFalse(factura.es_anulable)

    def test_anular_factura_ya_anulada_falla(self):
        """No se puede volver a anular una factura que ya está en estado ANULADA."""
        factura = FacturaService.emitir_factura(self.operacion)
        FacturaService.anular_factura(factura, self.user_cajero, "Primera anulación válida")

        resultado = FacturaService.anular_factura(factura, self.user_admin, "Segundo intento")
        self.assertFalse(resultado["exito"])
        self.assertIn("no puede anularse", resultado["error"])

    def test_vista_anular_factura_requiere_rol_autorizado(self):
        """Solo personal con rol cajero/admin puede ejecutar la anulación vía vista POST."""
        factura = FacturaService.emitir_factura(self.operacion)
        anular_url = reverse("pagos:anular_factura", kwargs={"factura_id": factura.id})

        # Cliente normal intenta anular
        self.client.login(username="cliente_maria", password="password123")
        res_cliente = self.client.post(
            anular_url, {"motivo": "Quiero anularla porque me equivoqué"}
        )
        factura.refresh_from_db()
        self.assertEqual(factura.estado, FacturaElectronica.EstadoFactura.EMITIDA)

        # Cajero (operador) anula con motivo válido
        self.client.login(username="cajero_juan", password="password123")
        res_cajero = self.client.post(
            anular_url, {"motivo": "Anulación solicitada formalmente por el cliente"}
        )
        self.assertEqual(res_cajero.status_code, 302)
        factura.refresh_from_db()
        self.assertEqual(factura.estado, FacturaElectronica.EstadoFactura.ANULADA)

    def test_rnf37_simulacion_tiempo_respuesta(self):
        """RNF37: La simulación de emisión se completa en ≤ 5 segundos."""
        import time
        inicio = time.time()
        factura = FacturaService.emitir_factura(self.operacion)
        duracion = time.time() - inicio

        self.assertLess(duracion, 5.0, "La emisión simulada debe tardar menos de 5 segundos.")
        self.assertEqual(factura.estado, FacturaElectronica.EstadoFactura.EMITIDA)
