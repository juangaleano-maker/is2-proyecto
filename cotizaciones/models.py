from django.db import models

class Cotizacion(models.Model):
    moneda_origen = models.ForeignKey(
        'monedas.Moneda', 
        on_delete=models.RESTRICT, 
        related_name='cotizaciones_origen', 
        limit_choices_to={'activa': True},
        verbose_name="Moneda Origen"
    )
    moneda_destino = models.ForeignKey(
        'monedas.Moneda', 
        on_delete=models.RESTRICT, 
        related_name='cotizaciones_destino', 
        limit_choices_to={'activa': True},
        verbose_name="Moneda Destino"
    )
    
    compra = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio de Compra")
    venta = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio de Venta")
    
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")
    activo = models.BooleanField(default=True, verbose_name="Estado Activo")
    registrado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Registrado por",
        related_name='cotizaciones_registradas'
    )

    class Meta:
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.moneda_origen.siglas} a {self.moneda_destino.siglas} - Compra: {self.compra} / Venta: {self.venta} ({self.fecha.strftime('%d/%m/%Y %H:%M')})"


class Operacion(models.Model):
    class TipoOperacion(models.TextChoices):
        COMPRA = "COMPRA", "Compra"
        VENTA = "VENTA", "Venta"

    class EstadoOperacion(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PAGADA = "PAGADA", "Pagada"
        CANCELADA = "CANCELADA", "Cancelada"

    cliente = models.ForeignKey(
        'clientes.Cliente', 
        on_delete=models.RESTRICT, 
        related_name='operaciones',
        verbose_name="Cliente"
    )
    moneda = models.ForeignKey(
        'monedas.Moneda', 
        on_delete=models.RESTRICT, 
        related_name='operaciones',
        verbose_name="Moneda"
    )
    tipo = models.CharField(
        max_length=10, 
        choices=TipoOperacion.choices, 
        verbose_name="Tipo de Operación"
    )
    monto = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        verbose_name="Monto"
    )
    tasa_aplicada = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        verbose_name="Tasa Aplicada"
    )
    comision = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00,
        verbose_name="Comisión"
    )
    fecha = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Fecha de Registro"
    )
    estado = models.CharField(
        max_length=15, 
        choices=EstadoOperacion.choices, 
        default=EstadoOperacion.PENDIENTE,
        verbose_name="Estado"
    )

    class Meta:
        verbose_name = "Operación"
        verbose_name_plural = "Operaciones"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.monto} {self.moneda.siglas} ({self.cliente})"
