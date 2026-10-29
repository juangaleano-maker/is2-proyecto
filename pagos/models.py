"""
Modelos del módulo de pagos.

Contiene:
- ComprobanteSIPAP: Comprobante adjunto por el cliente para confirmación manual.
- StripeEventoProcesado: Registro de eventos Stripe ya procesados (idempotencia).
- TicketTransaccion: Registro inmutable del ticket generado al completar un pago.
- FacturaElectronica: Factura electrónica simulada (IS2-63 / RF33-RF34-RNF37).
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError


def comprobante_upload_path(instance, filename):
    """Ruta de almacenamiento para comprobantes SIPAP."""
    ext = filename.rsplit(".", 1)[-1].lower()
    nuevo_nombre = f"{uuid.uuid4().hex}.{ext}"
    return f"comprobantes_sipap/{instance.operacion_id}/{nuevo_nombre}"


def validar_tamano_archivo(archivo):
    """Valida que el archivo no supere 5 MB."""
    limite_mb = 5
    if archivo.size > limite_mb * 1024 * 1024:
        raise ValidationError(
            f"El archivo no puede superar {limite_mb} MB. "
            f"Tamaño recibido: {archivo.size / (1024*1024):.2f} MB."
        )


class ComprobanteSIPAP(models.Model):
    """
    Comprobante de pago adjunto por el cliente para el flujo SIPAP.

    El cliente adjunta una imagen o PDF como evidencia de transferencia.
    Un cajero o administrador debe verificar y confirmar (o rechazar) manualmente.
    """

    class EstadoComprobante(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de revisión"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    operacion = models.OneToOneField(
        "cotizaciones.Operacion",
        on_delete=models.CASCADE,
        related_name="comprobante_sipap",
        verbose_name="Operación",
    )
    archivo = models.FileField(
        upload_to=comprobante_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["jpg", "jpeg", "png", "pdf"],
                message="Solo se aceptan archivos JPG, PNG o PDF.",
            ),
            validar_tamano_archivo,
        ],
        verbose_name="Archivo del comprobante",
    )
    estado = models.CharField(
        max_length=15,
        choices=EstadoComprobante.choices,
        default=EstadoComprobante.PENDIENTE,
        verbose_name="Estado de revisión",
    )
    subido_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comprobantes_subidos",
        verbose_name="Subido por",
    )
    revisado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comprobantes_revisados",
        verbose_name="Revisado por",
    )
    fecha_subida = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de subida")
    fecha_revision = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha de revisión"
    )
    motivo_rechazo = models.TextField(
        blank=True,
        verbose_name="Motivo de rechazo",
        help_text="Completar únicamente si se rechaza el comprobante.",
    )

    class Meta:
        verbose_name = "Comprobante SIPAP"
        verbose_name_plural = "Comprobantes SIPAP"
        ordering = ["-fecha_subida"]

    def __str__(self):
        return f"Comprobante #{self.pk} — Operación #{self.operacion_id} [{self.get_estado_display()}]"


class StripeEventoProcesado(models.Model):
    """
    Registro de eventos de Stripe ya procesados.

    Garantiza la idempotencia del webhook: si Stripe reenvía un evento
    que ya fue procesado, se ignora silenciosamente.
    """

    event_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        verbose_name="Stripe Event ID",
    )
    tipo_evento = models.CharField(max_length=100, verbose_name="Tipo de evento")
    procesado_en = models.DateTimeField(auto_now_add=True, verbose_name="Procesado el")
    datos_resumen = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Resumen del evento",
        help_text="Subconjunto de metadatos del evento para auditoría.",
    )

    class Meta:
        verbose_name = "Evento Stripe Procesado"
        verbose_name_plural = "Eventos Stripe Procesados"
        ordering = ["-procesado_en"]

    def __str__(self):
        return f"{self.tipo_evento} — {self.event_id}"


class TicketTransaccion(models.Model):
    """
    Ticket de transacción inmutable generado al completar un pago.

    Se crea automáticamente cuando una operación pasa al estado PAGADA
    (vía Stripe o confirmación manual SIPAP). Una vez generado, sus datos
    no deben modificarse para garantizar la integridad del registro contable.

    Campos auditables:
    - numero_ticket: identificador único legible (UUID corto).
    - referencia_externa: Stripe Payment Intent ID o referencia SIPAP.
    - cajero: usuario que confirmó (solo para flujo manual).
    """

    class MetodoPago(models.TextChoices):
        STRIPE = "STRIPE", "Stripe"
        SIPAP = "SIPAP", "SIPAP (Manual)"

    numero_ticket = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        verbose_name="Número de ticket",
    )
    operacion = models.OneToOneField(
        "cotizaciones.Operacion",
        on_delete=models.PROTECT,
        related_name="ticket",
        verbose_name="Operación",
    )
    cliente_nombre = models.CharField(max_length=255, verbose_name="Cliente (snapshot)")
    cliente_documento = models.CharField(max_length=50, verbose_name="Documento (snapshot)")
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto")
    moneda_siglas = models.CharField(max_length=10, verbose_name="Moneda")
    tasa_aplicada = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Tasa aplicada"
    )
    comision = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Comisión"
    )
    total_neto = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Total neto"
    )
    metodo_pago = models.CharField(
        max_length=10,
        choices=MetodoPago.choices,
        verbose_name="Método de pago",
    )
    referencia_externa = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Referencia externa",
        help_text="Stripe Payment Intent ID o referencia SIPAP.",
    )
    cajero = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets_generados",
        verbose_name="Cajero (si fue manual)",
    )
    generado_en = models.DateTimeField(auto_now_add=True, verbose_name="Generado el")

    class Meta:
        verbose_name = "Ticket de Transacción"
        verbose_name_plural = "Tickets de Transacción"
        ordering = ["-generado_en"]

    def __str__(self):
        return f"Ticket {self.numero_ticket} — Operación #{self.operacion_id}"

    def save(self, *args, **kwargs):
        """Genera el número de ticket antes de la primera inserción."""
        if not self.numero_ticket:
            self.numero_ticket = self._generar_numero_ticket()
        super().save(*args, **kwargs)

    @staticmethod
    def _generar_numero_ticket():
        """Genera un número de ticket único con prefijo TKT."""
        sufijo = uuid.uuid4().hex[:8].upper()
        return f"TKT-{sufijo}"


# =============================================================================
# IS2-63: Factura Electrónica simulada (RF33, RF34, RNF37)
# =============================================================================


class FacturaElectronica(models.Model):
    """
    Registro de la factura electrónica simulada asociada a una operación pagada.

    Criterios IS2-63:
    - RF33: El sistema permitirá generar facturas electrónicas asociadas a las
      transacciones realizadas.
    - RF34: El sistema permitirá gestionar el estado de las facturas electrónicas,
      pudiendo ser emitidas, aprobadas o rechazadas.
    - RNF37: La simulación de emisión (e-Kuatia) debe completarse en ≤ 5 segundos.

    Estados:
    - PENDIENTE: Generada pero aún no procesada por el simulador SIFEN.
    - EMITIDA:   Procesada y aprobada por el simulador (CDC asignado).
    - ANULADA:   Anulada manualmente por un admin/cajero.
    - RECHAZADA: Rechazada por el simulador (error de validación).

    El CDC (Código de Control 44 dígitos) y el número correlativo son simulados;
    en producción se reemplazarían por llamadas reales a la API de Factura Segura.
    """

    class EstadoFactura(models.TextChoices):
        PENDIENTE  = "PENDIENTE",  "Pendiente"
        EMITIDA    = "EMITIDA",    "Emitida"
        ANULADA    = "ANULADA",    "Anulada"
        RECHAZADA  = "RECHAZADA",  "Rechazada"

    class CondicionVenta(models.TextChoices):
        CONTADO = "CONTADO", "Contado"
        CREDITO = "CREDITO", "Crédito"

    # ── Relaciones ──────────────────────────────────────────────────────────
    operacion = models.OneToOneField(
        "cotizaciones.Operacion",
        on_delete=models.PROTECT,
        related_name="factura_electronica",
        verbose_name="Operación",
    )
    ticket = models.OneToOneField(
        TicketTransaccion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="factura_electronica",
        verbose_name="Ticket de transacción",
    )

    # ── Identificadores ──────────────────────────────────────────────────────
    numero_factura = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        verbose_name="Número de factura",
        help_text="Formato correlativo: 001-001-XXXXXXX",
    )
    cdc = models.CharField(
        max_length=44,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="CDC (Código de Control)",
        help_text="Identificador electrónico único de 44 dígitos (simulado).",
    )

    # ── Estado y condición ───────────────────────────────────────────────────
    estado = models.CharField(
        max_length=15,
        choices=EstadoFactura.choices,
        default=EstadoFactura.PENDIENTE,
        verbose_name="Estado",
    )
    condicion_venta = models.CharField(
        max_length=10,
        choices=CondicionVenta.choices,
        default=CondicionVenta.CONTADO,
        verbose_name="Condición de venta",
    )

    # ── Snapshot fiscal (requerido por SIFEN / e-Kuatia) ─────────────────────
    cliente_nombre = models.CharField(
        max_length=255,
        verbose_name="Nombre del receptor (snapshot)",
    )
    cliente_documento = models.CharField(
        max_length=50,
        verbose_name="Documento del receptor (snapshot)",
    )
    cliente_email = models.EmailField(
        blank=True,
        verbose_name="Email del receptor (snapshot)",
    )
    moneda_siglas = models.CharField(
        max_length=10,
        verbose_name="Moneda de la operación",
    )

    # ── Desglose tributario ──────────────────────────────────────────────────
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto en divisa",
    )
    tasa_aplicada = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Tasa de cambio aplicada",
    )
    base_imponible = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Base imponible (Gs.)",
        help_text="Subtotal en guaraníes antes del IVA.",
    )
    iva_liquidado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="IVA liquidado (Gs.)",
        help_text="IVA calculado sobre la base imponible.",
    )
    total_liquidado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Total liquidado (Gs.)",
        help_text="Base imponible + IVA liquidado.",
    )

    # ── Metadatos ────────────────────────────────────────────────────────────
    fecha_emision = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha y hora de emisión",
    )
    fecha_procesado = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de procesamiento SIFEN",
    )
    motivo_anulacion = models.TextField(
        blank=True,
        verbose_name="Motivo de anulación",
        help_text="Completar únicamente si se anula la factura.",
    )
    anulada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facturas_anuladas",
        verbose_name="Anulada por",
    )
    respuesta_simulador = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Respuesta del simulador",
        help_text="Datos devueltos por el simulador SIFEN para auditoría.",
    )

    class Meta:
        verbose_name = "Factura Electrónica"
        verbose_name_plural = "Facturas Electrónicas"
        ordering = ["-fecha_emision"]

    def __str__(self):
        return (
            f"Factura {self.numero_factura} "
            f"— {self.cliente_nombre} "
            f"[{self.get_estado_display()}]"
        )

    def save(self, *args, **kwargs):
        """Genera el número de factura correlativo antes de la primera inserción."""
        if not self.numero_factura:
            self.numero_factura = self._generar_numero_factura()
        super().save(*args, **kwargs)

    @staticmethod
    def _generar_numero_factura() -> str:
        """
        Genera un número de factura correlativo único con formato 001-003-XXXXXXX.

        Utiliza el establecimiento (001) y punto de expedición (003) autorizados
        por Factura Segura / SIFEN. El rango autorizado inicia en 0000326.
        """
        from django.conf import settings
        est = getattr(settings, "FACTURA_SEGURA_ESTABLECIMIENTO", "001")
        punto = getattr(settings, "FACTURA_SEGURA_PUNTO_EXPEDICION", "003")
        rango_inicio = getattr(settings, "FACTURA_SEGURA_RANGO_INICIAL", 326)

        total_previas = FacturaElectronica.objects.count()
        siguiente = rango_inicio + total_previas
        return f"{est}-{punto}-{siguiente:07d}"


    @property
    def es_anulable(self) -> bool:
        """Una factura puede anularse si está EMITIDA."""
        return self.estado == FacturaElectronica.EstadoFactura.EMITIDA

    @property
    def es_simulada(self) -> bool:
        """Indica si la factura fue emitida en modo simulación local."""
        if not self.respuesta_simulador:
            return True
        return bool(self.respuesta_simulador.get("simulado", True))
