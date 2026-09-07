from django.db import models

class Cotizacion(models.Model):
    MONEDAS = [
        ('USD', 'Dólar Estadounidense'),
        ('PYG', 'Guaraní'),
        ('ARS', 'Peso Argentino'),
        ('BRL', 'Real Brasileño'),
    ]

    moneda_origen = models.CharField(max_length=3, choices=MONEDAS, default='USD', verbose_name="Moneda Origen")
    moneda_destino = models.CharField(max_length=3, choices=MONEDAS, default='PYG', verbose_name="Moneda Destino")
    
    compra = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio de Compra")
    venta = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio de Venta")
    
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")
    activo = models.BooleanField(default=True, verbose_name="Estado Activo") # Para el futuro IS2-50

    class Meta:
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.moneda_origen} a {self.moneda_destino} - Compra: {self.compra} / Venta: {self.venta} ({self.fecha.strftime('%d/%m/%Y %H:%M')})"
