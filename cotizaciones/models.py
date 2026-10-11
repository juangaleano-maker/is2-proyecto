from django.db import models
from decimal import Decimal

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
    registrado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Registrado por",
        related_name='operaciones_registradas'
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


class SesionCaja(models.Model):
    """
    Modelo para el control de apertura y cierre de caja por turno (IS2-60).
    Registra el fondo inicial, movimientos del turno y el arqueo al cierre.
    """

    class EstadoSesion(models.TextChoices):
        ABIERTA = 'ABIERTA', 'Abierta'
        CERRADA = 'CERRADA', 'Cerrada'

    cajero = models.ForeignKey(
        'auth.User',
        on_delete=models.RESTRICT,
        related_name='sesiones_caja',
        verbose_name='Cajero',
    )
    nombre_caja = models.CharField(
        max_length=100,
        default='Caja Principal',
        verbose_name='Nombre / Identificador de Caja',
    )
    fecha_apertura = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha y Hora de Apertura',
    )
    monto_inicial = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Monto Inicial (Fondo de Caja)',
    )
    fecha_cierre = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha y Hora de Cierre',
    )
    monto_final_declarado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto Final Declarado',
    )
    saldo_esperado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Saldo Esperado',
    )
    diferencia = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Diferencia (+ Sobrante / - Faltante)',
    )
    estado = models.CharField(
        max_length=10,
        choices=EstadoSesion.choices,
        default=EstadoSesion.ABIERTA,
        verbose_name='Estado de Sesión',
    )
    observaciones = models.TextField(
        blank=True,
        default='',
        verbose_name='Observaciones de Cierre',
    )

    class Meta:
        verbose_name = 'Sesión de Caja'
        verbose_name_plural = 'Sesiones de Caja'
        ordering = ['-fecha_apertura']

    def __str__(self):
        return (
            f"{self.nombre_caja} — {self.cajero.get_full_name() or self.cajero.username} "
            f"({self.get_estado_display()}) [{self.fecha_apertura.strftime('%d/%m/%Y %H:%M')}]"
        )

    # ------------------------------------------------------------------
    # Lógica de negocio
    # ------------------------------------------------------------------

    def calcular_ingresos_turno(self):
        """
        Suma los subtotales de las operaciones PAGADAS registradas por este
        cajero durante el turno actual (entre apertura y cierre/ahora).
        Las operaciones de COMPRA son ingresos de moneda local;
        las de VENTA son egresos de moneda local.
        """
        from django.utils import timezone

        fin = self.fecha_cierre or timezone.now()
        ops = Operacion.objects.filter(
            registrado_por=self.cajero,
            estado=Operacion.EstadoOperacion.PAGADA,
            fecha__gte=self.fecha_apertura,
            fecha__lte=fin,
        )
        ingresos = Decimal('0.00')
        egresos = Decimal('0.00')
        for op in ops:
            subtotal = op.subtotal
            if op.tipo == Operacion.TipoOperacion.COMPRA:
                # El cajero paga moneda extranjera → recibe moneda local
                ingresos += subtotal
            else:
                # El cajero recibe moneda extranjera → entrega moneda local
                egresos += subtotal
        return ingresos, egresos

    def calcular_saldo_esperado(self):
        """Retorna el saldo esperado = monto_inicial + ingresos - egresos."""
        ingresos, egresos = self.calcular_ingresos_turno()
        return self.monto_inicial + ingresos - egresos

    def cerrar(self, monto_final_declarado, observaciones=''):
        """
        Cierra la sesión de caja calculando el saldo esperado y la diferencia.
        Persiste los cambios en la base de datos.
        """
        from django.utils import timezone
        from decimal import ROUND_HALF_UP

        self.fecha_cierre = timezone.now()
        self.monto_final_declarado = Decimal(str(monto_final_declarado))
        self.saldo_esperado = self.calcular_saldo_esperado().quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        self.diferencia = (
            self.monto_final_declarado - self.saldo_esperado
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.observaciones = observaciones
        self.estado = self.EstadoSesion.CERRADA
        self.save()

    @property
    def tipo_diferencia(self):
        """Retorna 'EXACTO', 'SOBRANTE' o 'FALTANTE' según la diferencia."""
        if self.diferencia is None:
            return None
        if self.diferencia > Decimal('0.00'):
            return 'SOBRANTE'
        if self.diferencia < Decimal('0.00'):
            return 'FALTANTE'
        return 'EXACTO'

