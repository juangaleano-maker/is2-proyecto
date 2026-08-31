from django.db import models
from clientes.models import Cliente


class UsuarioCliente(models.Model):
    """Representa un usuario del sistema vinculado a un cliente."""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='usuarios_asignados')
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    rol = models.CharField(max_length=50, default='Empleado')

    def __str__(self):
        return f"{self.nombre} {self.apellido} → {self.cliente.nombre}"
