import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class EstadoUsuario(models.TextChoices):
    PENDIENTE_VERIFICACION = 'PENDIENTE_VERIFICACION', 'Pendiente de verificación'
    ACTIVO = 'ACTIVO', 'Activo'
    INACTIVO = 'INACTIVO', 'Inactivo'
    BLOQUEADO = 'BLOQUEADO', 'Bloqueado'


class PerfilUsuario(models.Model):
    """
    Perfil extendido de usuario que maneja el estado de verificación,
    la vinculación con Keycloak y los tokens de verificación por correo.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='perfil',
        verbose_name='Usuario del sistema'
    )
    keycloak_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        unique=True,
        verbose_name='ID en Keycloak',
        help_text='Identificador único (UUID) asignado por Keycloak'
    )
    estado = models.CharField(
        max_length=30,
        choices=EstadoUsuario.choices,
        default=EstadoUsuario.PENDIENTE_VERIFICACION,
        verbose_name='Estado de la cuenta'
    )
    email_verificado = models.BooleanField(
        default=False,
        verbose_name='Correo verificado'
    )
    token_verificacion = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        db_index=True,
        verbose_name='Token de verificación'
    )
    token_expiracion = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Expiración del token'
    )
    creado_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    actualizado_en = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuarios'
        ordering = ['-creado_en']

    def __str__(self):
        return f"{self.user.username} - {self.get_estado_display()} ({'Verificado' if self.email_verificado else 'No verificado'})"

    def generar_token_verificacion(self):
        """
        Genera un token seguro y define su fecha de expiración.
        """
        self.token_verificacion = secrets.token_urlsafe(32)
        expiration_hours = getattr(settings, 'EMAIL_TOKEN_EXPIRATION_HOURS', 24)
        self.token_expiracion = timezone.now() + timedelta(hours=expiration_hours)
        self.save(update_fields=['token_verificacion', 'token_expiracion', 'actualizado_en'])
        return self.token_verificacion

    def is_token_valido(self, token_ingresado):
        """
        Verifica si el token proporcionado coincide y no ha expirado.
        """
        if not self.token_verificacion or not self.token_expiracion:
            return False
        if self.token_verificacion != token_ingresado:
            return False
        if timezone.now() > self.token_expiracion:
            return False
        return True

    def activar_cuenta(self):
        """
        Activa la cuenta tras la verificación exitosa del correo.
        """
        self.estado = EstadoUsuario.ACTIVO
        self.email_verificado = True
        self.token_verificacion = None
        self.token_expiracion = None
        self.save()

        # Activar el usuario base de Django
        if not self.user.is_active:
            self.user.is_active = True
            self.user.save(update_fields=['is_active'])

    @property
    def esta_activo(self):
        """
        Indica si el usuario está completamente activo y habilitado para operar.
        """
        return self.estado == EstadoUsuario.ACTIVO and self.email_verificado and self.user.is_active
