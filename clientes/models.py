
from django.db import models

class Cliente(models.Model):
    class TipoPersona(models.TextChoices):
        FISICA = "FISICA", "Persona Física"
        JURIDICA = "JURIDICA", "Persona Jurídica"

    class Segmento(models.TextChoices):
        MINORISTA = "MINORISTA", "Minorista"
        CORPORATIVO = "CORPORATIVO", "Corporativo"
        VIP = "VIP", "VIP"

    tipo_persona = models.CharField(max_length=10, choices=TipoPersona.choices)
    segmento = models.CharField(max_length=15, choices=Segmento.choices, default=Segmento.MINORISTA)

    # Identificador único (CI o RUC según tipo)
    documento = models.CharField(max_length=20, unique=True)

    # Persona física
    nombre = models.CharField(max_length=100, blank=True)
    apellido = models.CharField(max_length=100, blank=True)

    # Persona jurídica
    razon_social = models.CharField(max_length=150, blank=True)

    email = models.EmailField()
    telefono = models.CharField(max_length=20, blank=True)
    direccion = models.CharField(max_length=200, blank=True)

    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.razon_social if self.tipo_persona == self.TipoPersona.JURIDICA else f"{self.nombre} {self.apellido}"

class MedioDePago(models.Model):
    class TipoMedio(models.TextChoices):
        TARJETA_CREDITO = "TARJETA_CREDITO", "Tarjeta de Crédito"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia Bancaria"
        EFECTIVO = "EFECTIVO", "Efectivo"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="medios_de_pago")
    tipo = models.CharField(max_length=20, choices=TipoMedio.choices)
    entidad = models.CharField(max_length=100, blank=True, null=True, help_text="Nombre del Banco o Entidad emisora")
    numero = models.CharField(max_length=50, blank=True, null=True, help_text="Número de cuenta o tarjeta")
    titular = models.CharField(max_length=150, blank=True, null=True, help_text="Nombre del titular")
    
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.tipo == self.TipoMedio.EFECTIVO:
            return f"Efectivo - {self.cliente}"
        return f"{self.get_tipo_display()} - {self.entidad or 'Sin Entidad'} - {self.numero or 'N/A'}"
