"""
Migración IS2-63: Tabla FacturaElectronica.

Crea la tabla pagos_facturaelectronica que almacena:
- La relación OneToOne con Operacion (protected) y con TicketTransaccion (set_null).
- El número correlativo de factura (001-001-XXXXXXX) y el CDC simulado de 44 chars.
- Estados: PENDIENTE, EMITIDA, ANULADA, RECHAZADA.
- Desglose fiscal: monto, tasa, base_imponible, iva_liquidado, total_liquidado.
- Snapshot del receptor: nombre, documento, email.
- Metadatos: fecha_emision, fecha_procesado, motivo_anulacion, anulada_por,
  respuesta_simulador (JSON).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pagos", "0001_initial"),
        ("cotizaciones", "0010_caja_conteobilletesesion_cantidad_sistema_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FacturaElectronica",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                # ── Identificadores ──────────────────────────────────────────
                (
                    "numero_factura",
                    models.CharField(
                        editable=False,
                        max_length=20,
                        unique=True,
                        verbose_name="Número de factura",
                        help_text="Formato correlativo: 001-001-XXXXXXX",
                    ),
                ),
                (
                    "cdc",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Identificador electrónico único de 44 dígitos (simulado).",
                        max_length=44,
                        null=True,
                        unique=True,
                        verbose_name="CDC (Código de Control)",
                    ),
                ),
                # ── Estado ───────────────────────────────────────────────────
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente"),
                            ("EMITIDA", "Emitida"),
                            ("ANULADA", "Anulada"),
                            ("RECHAZADA", "Rechazada"),
                        ],
                        default="PENDIENTE",
                        max_length=15,
                        verbose_name="Estado",
                    ),
                ),
                (
                    "condicion_venta",
                    models.CharField(
                        choices=[
                            ("CONTADO", "Contado"),
                            ("CREDITO", "Crédito"),
                        ],
                        default="CONTADO",
                        max_length=10,
                        verbose_name="Condición de venta",
                    ),
                ),
                # ── Snapshot del receptor ────────────────────────────────────
                (
                    "cliente_nombre",
                    models.CharField(
                        max_length=255,
                        verbose_name="Nombre del receptor (snapshot)",
                    ),
                ),
                (
                    "cliente_documento",
                    models.CharField(
                        max_length=50,
                        verbose_name="Documento del receptor (snapshot)",
                    ),
                ),
                (
                    "cliente_email",
                    models.EmailField(
                        blank=True,
                        verbose_name="Email del receptor (snapshot)",
                    ),
                ),
                (
                    "moneda_siglas",
                    models.CharField(
                        max_length=10,
                        verbose_name="Moneda de la operación",
                    ),
                ),
                # ── Desglose tributario ──────────────────────────────────────
                (
                    "monto",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        verbose_name="Monto en divisa",
                    ),
                ),
                (
                    "tasa_aplicada",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        verbose_name="Tasa de cambio aplicada",
                    ),
                ),
                (
                    "base_imponible",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Subtotal en guaraníes antes del IVA.",
                        max_digits=14,
                        verbose_name="Base imponible (Gs.)",
                    ),
                ),
                (
                    "iva_liquidado",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="IVA calculado sobre la base imponible.",
                        max_digits=14,
                        verbose_name="IVA liquidado (Gs.)",
                    ),
                ),
                (
                    "total_liquidado",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Base imponible + IVA liquidado.",
                        max_digits=14,
                        verbose_name="Total liquidado (Gs.)",
                    ),
                ),
                # ── Metadatos ────────────────────────────────────────────────
                (
                    "fecha_emision",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Fecha y hora de emisión",
                    ),
                ),
                (
                    "fecha_procesado",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Fecha de procesamiento SIFEN",
                    ),
                ),
                (
                    "motivo_anulacion",
                    models.TextField(
                        blank=True,
                        help_text="Completar únicamente si se anula la factura.",
                        verbose_name="Motivo de anulación",
                    ),
                ),
                (
                    "respuesta_simulador",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Datos devueltos por el simulador SIFEN para auditoría.",
                        verbose_name="Respuesta del simulador",
                    ),
                ),
                # ── FK ───────────────────────────────────────────────────────
                (
                    "anulada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="facturas_anuladas",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Anulada por",
                    ),
                ),
                (
                    "operacion",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="factura_electronica",
                        to="cotizaciones.operacion",
                        verbose_name="Operación",
                    ),
                ),
                (
                    "ticket",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="factura_electronica",
                        to="pagos.tickettransaccion",
                        verbose_name="Ticket de transacción",
                    ),
                ),
            ],
            options={
                "verbose_name": "Factura Electrónica",
                "verbose_name_plural": "Facturas Electrónicas",
                "ordering": ["-fecha_emision"],
            },
        ),
    ]
