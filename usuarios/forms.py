import re
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import EstadoUsuario, PerfilUsuario


class RegistroUsuarioForm(forms.ModelForm):
    """
    Formulario público de autoregistro de usuarios para Global Exchange.
    Aplica validaciones estrictas de seguridad de contraseña (RNF24)
    y asegura unicidad de usuario y correo.
    """
    first_name = forms.CharField(
        label="Nombres",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej. Juan Carlos',
            'autocomplete': 'given-name'
        })
    )
    last_name = forms.CharField(
        label="Apellidos",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej. Pérez González',
            'autocomplete': 'family-name'
        })
    )
    username = forms.CharField(
        label="Nombre de Usuario",
        max_length=150,
        required=True,
        help_text="Solo letras, números y @/./+/-/_",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej. jperez',
            'autocomplete': 'username'
        })
    )
    email = forms.EmailField(
        label="Correo Electrónico",
        required=True,
        help_text="Enviaremos un enlace de verificación a esta dirección.",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'usuario@dominio.com',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        label="Contraseña",
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
            'autocomplete': 'new-password'
        }),
        help_text="Mínimo 8 caracteres, al menos una mayúscula, un número y un carácter especial."
    )
    password_confirm = forms.CharField(
        label="Confirmar Contraseña",
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
            'autocomplete': 'new-password'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Este nombre de usuario ya está registrado en el sistema.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Ya existe una cuenta registrada con este correo electrónico.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not password:
            return password

        # Validación RNF24: Mínimo 8 caracteres, al menos una mayúscula, un número y un carácter especial
        if len(password) < 8:
            raise ValidationError("La contraseña debe tener al menos 8 caracteres.")
        if not re.search(r'[A-Z]', password):
            raise ValidationError("La contraseña debe incluir al menos una letra mayúscula.")
        if not re.search(r'[0-9]', password):
            raise ValidationError("La contraseña debe incluir al menos un número.")
        if not re.search(r'[^A-Za-z0-9]', password):
            raise ValidationError("La contraseña debe incluir al menos un carácter especial (ej. !@#$%^&*).")

        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', "Las contraseñas ingresadas no coinciden.")

        return cleaned_data


class ReenviarCorreoForm(forms.Form):
    """
    Formulario para solicitar el reenvío del correo de verificación.
    """
    email = forms.EmailField(
        label="Correo Electrónico",
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingresa tu correo registrado',
            'autocomplete': 'email'
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
            if hasattr(user, 'perfil') and user.perfil.estado == EstadoUsuario.ACTIVO:
                raise ValidationError("Esta cuenta ya se encuentra verificada y activa. Puedes iniciar sesión directamente.")
        except User.DoesNotExist:
            raise ValidationError("No existe ninguna cuenta registrada con este correo electrónico.")
        return email
