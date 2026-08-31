
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