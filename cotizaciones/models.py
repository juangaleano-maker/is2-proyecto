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
        PENDIENTE_CONFIRMACION = "PENDIENTE_CONFIRMACION", "Pendiente de confirmación"
        PAGADA = "PAGADA", "Pagada"
        CANCELADA = "CANCELADA", "Cancelada"
        PAGO_FALLIDO = "PAGO_FALLIDO", "Pago fallido"
        RECHAZADA = "RECHAZADA", "Rechazada"

    class CanalOperacion(models.TextChoices):
        FISICO = "FISICO", "Canal Físico (Caja)"
        DIGITAL = "DIGITAL", "Canal Digital / Web"

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
    caja = models.ForeignKey(
        'Caja',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operaciones',
        verbose_name="Caja Física",
        help_text="Punto físico de atención asignado donde se realizó la operación (canal físico - RN15)."
    )
    sesion_caja = models.ForeignKey(
        'SesionCaja',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operaciones',
        verbose_name="Turno / Sesión de Caja",
        help_text="Turno de caja durante el cual se procesó la operación (RN15/RN16)."
    )
    canal = models.CharField(
        max_length=15,
        choices=CanalOperacion.choices,
        default=CanalOperacion.DIGITAL,
        verbose_name="Canal de Atención",
        help_text="Indica si la operación se realizó por ventanilla física o vía web."
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

    @property
    def movimiento_caja(self):
        """Retorna el primer movimiento de caja asociado (compatibilidad hacia atrás)."""
        return self.movimientos_caja.first() if hasattr(self, 'movimientos_caja') else None


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


class Caja(models.Model):
    """
    Punto físico de atención asignado a un cajero durante su turno,
    con stock propio de billetes por denominación (Definición ERS Pág. 4).
    """
    numero = models.PositiveIntegerField(unique=True, verbose_name="Número de Caja")
    nombre = models.CharField(max_length=100, verbose_name="Nombre / Ventanilla")
    sucursal = models.CharField(max_length=100, default="Casa Central", verbose_name="Sucursal")
    activa = models.BooleanField(default=True, verbose_name="Habilitada para Operar")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Caja Física"
        verbose_name_plural = "Cajas Físicas"
        ordering = ['numero']

    def __str__(self):
        return f"Caja #{self.numero} - {self.nombre} ({self.sucursal})"

    @property
    def sesion_activa(self):
        """Retorna el turno / sesión actualmente abierta en esta caja física."""
        return self.sesiones.filter(estado=SesionCaja.EstadoSesion.ABIERTA).first()

    @property
    def esta_abierta(self):
        """Indica si la caja se encuentra actualmente abierta por un turno activo (RN16)."""
        return self.sesion_activa is not None


class StockBilleteCaja(models.Model):
    """
    Stock propio de billetes físicos por denominación en una caja física (Definición ERS).
    """
    caja = models.ForeignKey(
        Caja,
        on_delete=models.CASCADE,
        related_name='stock_billetes',
        verbose_name='Caja Física'
    )
    denominacion = models.ForeignKey(
        'monedas.DenominacionMoneda',
        on_delete=models.CASCADE,
        related_name='stocks_caja',
        verbose_name='Denominación de Billete'
    )
    cantidad = models.PositiveIntegerField(
        default=0,
        verbose_name='Cantidad de Billetes en Stock'
    )

    class Meta:
        verbose_name = 'Stock de Billete en Caja'
        verbose_name_plural = 'Stock de Billetes en Caja'
        unique_together = ('caja', 'denominacion')

    def __str__(self):
        return f"{self.caja.nombre} - {self.cantidad}x {self.denominacion}"

    @property
    def subtotal(self):
        return Decimal(str(self.cantidad)) * self.denominacion.valor


class SesionCaja(models.Model):
    """
    Modelo para el control de apertura y cierre de caja por turno (IS2-60).
    Registra el fondo inicial, movimientos del turno y el arqueo al cierre.
    """

    class EstadoSesion(models.TextChoices):
        ABIERTA = 'ABIERTA', 'Abierta'
        CERRADA = 'CERRADA', 'Cerrada'

    caja = models.ForeignKey(
        Caja,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sesiones',
        verbose_name='Caja Física Asignada',
        help_text='Punto físico de atención asignado al cajero durante su turno (RN15).'
    )
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
        caja_info = f"{self.caja.nombre}" if self.caja else self.nombre_caja
        return (
            f"{caja_info} — {self.cajero.get_full_name() or self.cajero.username} "
            f"({self.get_estado_display()}) [{self.fecha_apertura.strftime('%d/%m/%Y %H:%M')}]"
        )

    def save(self, *args, **kwargs):
        if self.caja and (not self.nombre_caja or self.nombre_caja == 'Caja Principal'):
            self.nombre_caja = self.caja.nombre
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Lógica de negocio
    # ------------------------------------------------------------------

    def calcular_ingresos_turno(self):
        """
        Retorna la suma de ingresos y egresos registrados en la sesión
        a través de los MovimientoCaja asociados. Si no hay movimientos
        (ej. sesión previa a IS2-61), utiliza fallback sobre Operacion.
        """
        movs = self.movimientos.all()
        if movs.exists():
            from django.db.models import Sum
            ingresos = movs.filter(tipo='INGRESO').aggregate(s=Sum('monto'))['s'] or Decimal('0.00')
            egresos = movs.filter(tipo='EGRESO').aggregate(s=Sum('monto'))['s'] or Decimal('0.00')
            return ingresos, egresos

        # Fallback de compatibilidad
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
                ingresos += subtotal
            else:
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

    def calcular_ingresos_turno_por_moneda(self):
        """
        Retorna un diccionario agrupado por cada moneda activa:
        - Para PYG (moneda local): suma 'monto' según 'tipo'.
        - Para divisas extranjeras (USD, EUR, BRL): suma 'monto_divisa' según 'tipo_divisa'.
        """
        from monedas.models import Moneda
        from django.db.models import Sum

        monedas_activas = Moneda.objects.filter(activa=True)
        res = {}
        for m in monedas_activas:
            siglas = m.siglas.upper()
            if siglas == 'PYG':
                ing = self.movimientos.filter(tipo='INGRESO').aggregate(s=Sum('monto'))['s'] or Decimal('0.00')
                egr = self.movimientos.filter(tipo='EGRESO').aggregate(s=Sum('monto'))['s'] or Decimal('0.00')
            else:
                movs_m = self.movimientos.filter(moneda=m, monto_divisa__isnull=False)
                ing = movs_m.filter(tipo_divisa='INGRESO').aggregate(s=Sum('monto_divisa'))['s'] or Decimal('0.00')
                egr = movs_m.filter(tipo_divisa='EGRESO').aggregate(s=Sum('monto_divisa'))['s'] or Decimal('0.00')

            res[m.id] = {
                'moneda': m,
                'ingresos': ing,
                'egresos': egr,
                'saldo_neto': ing - egr,
            }
        return res

    def calcular_saldos_esperados_multidivisa(self):
        """
        Calcula el saldo esperado para cada moneda activa en la sesión.
        saldo_esperado = monto_inicial + ingresos - egresos.
        """
        from monedas.models import Moneda
        movs_por_moneda = self.calcular_ingresos_turno_por_moneda()
        saldos_existentes = {s.moneda_id: s for s in self.saldos_moneda.select_related('moneda')}

        resultado = []
        for m in Moneda.objects.filter(activa=True).order_by('id'):
            saldo_obj = saldos_existentes.get(m.id)
            if saldo_obj:
                inicial = saldo_obj.monto_inicial
                final_dec = saldo_obj.monto_final_declarado
            elif m.siglas.upper() == 'PYG':
                inicial = self.monto_inicial
                final_dec = self.monto_final_declarado
            else:
                inicial = Decimal('0.00')
                final_dec = None

            datos_movs = movs_por_moneda.get(m.id, {'ingresos': Decimal('0.00'), 'egresos': Decimal('0.00')})
            ingresos = datos_movs['ingresos']
            egresos = datos_movs['egresos']
            esperado = inicial + ingresos - egresos

            dif = (final_dec - esperado) if final_dec is not None else None
            tipo_dif = None
            if dif is not None:
                if dif == Decimal('0.00'):
                    tipo_dif = 'EXACTO'
                elif dif > Decimal('0.00'):
                    tipo_dif = 'SOBRANTE'
                else:
                    tipo_dif = 'FALTANTE'

            resultado.append({
                'moneda': m,
                'saldo_obj': saldo_obj,
                'monto_inicial': inicial,
                'ingresos': ingresos,
                'egresos': egresos,
                'saldo_esperado': esperado,
                'monto_final_declarado': final_dec,
                'diferencia': dif,
                'tipo_diferencia': tipo_dif,
            })
        return resultado


class MovimientoCaja(models.Model):
    """
    Registra cada movimiento de dinero (ingreso/egreso) asociado a una sesión
    de caja activa (IS2-61). Vincula operaciones de compra/venta y pagos confirmados.
    """
    class TipoMovimiento(models.TextChoices):
        INGRESO = 'INGRESO', 'Ingreso'
        EGRESO = 'EGRESO', 'Egreso'

    sesion = models.ForeignKey(
        SesionCaja,
        on_delete=models.CASCADE,
        related_name='movimientos',
        verbose_name='Sesión de Caja',
    )
    tipo = models.CharField(
        max_length=10,
        choices=TipoMovimiento.choices,
        verbose_name='Tipo de Movimiento (Moneda Local)',
    )
    monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Monto en Moneda Local (Gs.)',
    )
    moneda = models.ForeignKey(
        'monedas.Moneda',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_caja',
        verbose_name='Divisa Extranjera',
    )
    monto_divisa = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto en Divisa',
    )
    tipo_divisa = models.CharField(
        max_length=10,
        choices=TipoMovimiento.choices,
        null=True,
        blank=True,
        verbose_name='Tipo de Movimiento Divisa',
    )
    concepto = models.CharField(
        max_length=255,
        verbose_name='Concepto / Descripción',
    )
    operacion = models.OneToOneField(
        'Operacion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='movimiento_caja',
        verbose_name='Operación Asociada',
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha y Hora',
    )
    registrado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_caja_registrados',
        verbose_name='Registrado Por',
    )

    class Meta:
        verbose_name = 'Movimiento de Caja'
        verbose_name_plural = 'Movimientos de Caja'
        ordering = ['-fecha']

    def __str__(self):
        signo = '+' if self.tipo == self.TipoMovimiento.INGRESO else '-'
        siglas = self.moneda.siglas if self.moneda else 'Gs.'
        return f"{self.sesion.nombre_caja} | {self.tipo} ({signo}{siglas} {self.monto}) - {self.concepto}"


class SaldoSesionMoneda(models.Model):
    """
    Control de saldo inicial, movimientos y arqueo por cada moneda física activa
    en la sesión de caja (PYG, USD, EUR, BRL, etc.).
    """
    sesion = models.ForeignKey(
        SesionCaja,
        on_delete=models.CASCADE,
        related_name='saldos_moneda',
        verbose_name='Sesión de Caja'
    )
    moneda = models.ForeignKey(
        'monedas.Moneda',
        on_delete=models.PROTECT,
        related_name='saldos_caja',
        verbose_name='Moneda'
    )
    monto_inicial = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Fondo Inicial'
    )
    monto_final_declarado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto Final Declarado'
    )
    saldo_esperado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Saldo Esperado'
    )
    diferencia = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Diferencia (+ Sobrante / - Faltante)'
    )

    class Meta:
        verbose_name = 'Saldo de Sesión por Moneda'
        verbose_name_plural = 'Saldos de Sesión por Moneda'
        unique_together = ('sesion', 'moneda')

    def __str__(self):
        return f"{self.sesion.nombre_caja} - {self.moneda.siglas}: Inicial {self.monto_inicial}"

    @property
    def tipo_diferencia(self):
        if self.diferencia is None:
            return None
        if self.diferencia > Decimal('0.00'):
            return 'SOBRANTE'
        if self.diferencia < Decimal('0.00'):
            return 'FALTANTE'
        return 'EXACTO'


class ConteoBilleteSesion(models.Model):
    """
    Registra el desglose físico de billetes contados por denominación
    al momento de la apertura o del arqueo de cierre.
    """
    class MomentoConteo(models.TextChoices):
        APERTURA = 'APERTURA', 'Apertura'
        CIERRE = 'CIERRE', 'Arqueo de Cierre'

    sesion = models.ForeignKey(
        SesionCaja,
        on_delete=models.CASCADE,
        related_name='conteos_billetes',
        verbose_name='Sesión de Caja'
    )
    denominacion = models.ForeignKey(
        'monedas.DenominacionMoneda',
        on_delete=models.PROTECT,
        related_name='conteos_sesion',
        verbose_name='Denominación de Billete'
    )
    momento = models.CharField(
        max_length=15,
        choices=MomentoConteo.choices,
        verbose_name='Momento de Conteo'
    )
    cantidad = models.PositiveIntegerField(
        default=0,
        verbose_name='Cantidad de Billetes Contada'
    )
    cantidad_sistema = models.PositiveIntegerField(
        default=0,
        verbose_name='Cantidad de Billetes Registrada por Sistema'
    )
    diferencia_piezas = models.IntegerField(
        default=0,
        verbose_name='Diferencia de Piezas (+ Sobrante / - Faltante)'
    )

    class Meta:
        verbose_name = 'Conteo de Billete en Sesión'
        verbose_name_plural = 'Conteos de Billetes en Sesión'
        unique_together = ('sesion', 'denominacion', 'momento')

    def __str__(self):
        return f"{self.sesion.nombre_caja} [{self.momento}] - {self.cantidad}x {self.denominacion}"

    @property
    def subtotal(self):
        from decimal import Decimal
        return Decimal(str(self.cantidad)) * self.denominacion.valor

    @property
    def subtotal_sistema(self):
        from decimal import Decimal
        return Decimal(str(self.cantidad_sistema)) * self.denominacion.valor

    @property
    def diferencia_monto(self):
        from decimal import Decimal
        return Decimal(str(self.diferencia_piezas)) * self.denominacion.valor



