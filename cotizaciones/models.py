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
        PENDIENTE_CONFIRMACION = "PENDIENTE_CONFIRMACION", "Pendiente de confirmación"
        PAGADA = "PAGADA", "Pagada"
        CANCELADA = "CANCELADA", "Cancelada"
        PAGO_FALLIDO = "PAGO_FALLIDO", "Pago fallido"
        RECHAZADA = "RECHAZADA", "Rechazada"

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
        max_length=25,
        choices=EstadoOperacion.choices,
        default=EstadoOperacion.PENDIENTE,
        verbose_name="Estado"
    )
    registrado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Registrado por",
        related_name='operaciones_registradas'
    )
    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Stripe Payment Intent ID",
        help_text="ID del PaymentIntent en Stripe (solo flujo Stripe).",
    )

    class Meta:
        verbose_name = "Operación"
        verbose_name_plural = "Operaciones"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.monto} {self.moneda.siglas} ({self.cliente})"

    @property
    def subtotal(self):
        """Monto multiplicado por la tasa aplicada."""
        if self.monto is not None and self.tasa_aplicada is not None:
            from decimal import Decimal, ROUND_HALF_UP
            return (self.monto * self.tasa_aplicada).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        from decimal import Decimal
        return Decimal('0.00')

    @property
    def total_neto(self):
        """
        Total neto según el tipo de operación:
        - Venta: subtotal - comision (el cliente entrega divisa y recibe el neto en moneda local)
        - Compra: subtotal + comision (el cliente entrega moneda local + comision para recibir divisa)
        """
        from decimal import Decimal, ROUND_HALF_UP
        sub = self.subtotal
        com = self.comision or Decimal('0.00')
        if self.tipo == self.TipoOperacion.VENTA:
            return (sub - com).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return (sub + com).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class AlertaTasa(models.Model):
    """
    Configuración de alertas de tasas (IS2-57).
    Permite a los usuarios suscribirse a variaciones de monedas o definir
    umbrales de compra/venta para recibir notificaciones.
    """
    class TipoAlerta(models.TextChoices):
        VARIACION = "VARIACION", "Cualquier variación de tasa"
        COMPRA_MAYOR = "COMPRA_MAYOR", "Precio de compra mayor o igual a"
        COMPRA_MENOR = "COMPRA_MENOR", "Precio de compra menor o igual a"
        VENTA_MAYOR = "VENTA_MAYOR", "Precio de venta mayor o igual a"
        VENTA_MENOR = "VENTA_MENOR", "Precio de venta menor o igual a"

    usuario = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='alertas_tasa',
        verbose_name="Usuario"
    )
    moneda = models.ForeignKey(
        'monedas.Moneda',
        on_delete=models.CASCADE,
        related_name='alertas',
        limit_choices_to={'activa': True},
        verbose_name="Moneda"
    )
    tipo = models.CharField(
        max_length=20,
        choices=TipoAlerta.choices,
        default=TipoAlerta.VARIACION,
        verbose_name="Tipo de Alerta"
    )
    valor_objetivo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Valor Objetivo (Compra/Venta)"
    )
    activa = models.BooleanField(
        default=True,
        verbose_name="Alerta Activa"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación"
    )

    class Meta:
        verbose_name = "Alerta de Tasa"
        verbose_name_plural = "Alertas de Tasas"
        ordering = ['-fecha_creacion']

    def __str__(self):
        if self.tipo == self.TipoAlerta.VARIACION:
            return f"{self.usuario.username} - Monitoreo {self.moneda.siglas} (Cualquier variación)"
        return f"{self.usuario.username} - {self.moneda.siglas} ({self.get_tipo_display()} {self.valor_objetivo})"

    def se_cumple(self, cotizacion) -> bool:
        """Verifica si la cotización cumple la condición de esta alerta."""
        if not self.activa:
            return False
        if cotizacion.moneda_origen_id != self.moneda_id:
            return False
        if self.tipo == self.TipoAlerta.VARIACION:
            return True
        if self.valor_objetivo is None:
            return False
        if self.tipo == self.TipoAlerta.COMPRA_MAYOR:
            return cotizacion.compra >= self.valor_objetivo
        if self.tipo == self.TipoAlerta.COMPRA_MENOR:
            return cotizacion.compra <= self.valor_objetivo
        if self.tipo == self.TipoAlerta.VENTA_MAYOR:
            return cotizacion.venta >= self.valor_objetivo
        if self.tipo == self.TipoAlerta.VENTA_MENOR:
            return cotizacion.venta <= self.valor_objetivo
        return False


class NotificacionTasa(models.Model):
    """
    Notificaciones por variación de tasa (IS2-58).
    Generadas cuando una cotización se actualiza o alcanza las condiciones de una alerta.
    """
    usuario = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='notificaciones_tasa',
        verbose_name="Usuario"
    )
    moneda = models.ForeignKey(
        'monedas.Moneda',
        on_delete=models.CASCADE,
        related_name='notificaciones_tasas',
        verbose_name="Moneda"
    )
    cotizacion = models.ForeignKey(
        Cotizacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notificaciones',
        verbose_name="Cotización de Origen"
    )
    alerta = models.ForeignKey(
        AlertaTasa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notificaciones',
        verbose_name="Alerta que detonó"
    )
    titulo = models.CharField(
        max_length=200,
        verbose_name="Título"
    )
    mensaje = models.TextField(
        verbose_name="Mensaje descriptivo"
    )
    tasa_compra = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Tasa de Compra"
    )
    tasa_venta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Tasa de Venta"
    )
    fecha_actualizacion = models.DateTimeField(
        verbose_name="Fecha de Actualización"
    )
    leida = models.BooleanField(
        default=False,
        verbose_name="¿Leída?"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Notificación"
    )

    class Meta:
        verbose_name = "Notificación de Tasa"
        verbose_name_plural = "Notificaciones de Tasas"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"[{self.moneda.siglas}] {self.titulo} - Para: {self.usuario.username} ({'Leída' if self.leida else 'Nueva'})"


