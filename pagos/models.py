"""
Modelos del módulo de pagos.

Contiene:
- MetodoPagoSistema: Catálogo estático de métodos de pago habilitados en el sistema.
- ComprobanteSIPAP: Comprobante adjunto por el cliente para confirmación manual.
- StripeEventoProcesado: Registro de eventos Stripe ya procesados (idempotencia).
- TicketTransaccion: Registro inmutable del ticket generado al completar un pago.
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


class MetodoPagoSistema(models.Model):
    """
    Catálogo global y estático de métodos de pago habilitados en el sistema.

    Los administradores definen aquí los métodos disponibles (ej. Efectivo, Tarjeta
    de Crédito, Transferencia Bancaria, SIPAP, Stripe). Estos se asignan luego
    a clientes específicos mediante la relación M2M en el modelo Cliente.
    """

    class Categoria(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA_CREDITO = "TARJETA_CREDITO", "Tarjeta de Crédito"
        TARJETA_DEBITO = "TARJETA_DEBITO", "Tarjeta de Débito"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia Bancaria"
        DIGITAL = "DIGITAL", "Pago Digital / Online"
        OTRO = "OTRO", "Otro"

    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nombre del Método",
        help_text="Denominación visible para usuarios y operadores (ej. 'Tarjeta Visa Crédito').",
    )
    categoria = models.CharField(
        max_length=20,
        choices=Categoria.choices,
        default=Categoria.EFECTIVO,
        verbose_name="Categoría",
    )
    descripcion = models.TextField(
        blank=True,
        verbose_name="Descripción",
        help_text="Descripción detallada o instrucciones para el operador.",
    )
    icono = models.CharField(
        max_length=10,
        blank=True,
        default="💳",
        verbose_name="Ícono (emoji)",
        help_text="Emoji representativo del método de pago.",
    )
    activo = models.BooleanField(
        default=True,
        verbose_name="¿Habilitado?",
        help_text="Solo los métodos activos pueden asignarse a clientes y seleccionarse en operaciones.",
    )
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name="Actualizado el")

    class Meta:
        verbose_name = "Método de Pago del Sistema"
        verbose_name_plural = "Métodos de Pago del Sistema"
        ordering = ["categoria", "nombre"]

    def __str__(self):
        return f"{self.icono} {self.nombre} ({self.get_categoria_display()})"


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
