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
