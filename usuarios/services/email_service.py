import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags

from .keycloak_service import KeycloakAdminService

logger = logging.getLogger(__name__)


def enviar_correo_activacion(user, perfil, request=None):
    """
    Envía el correo electrónico con el enlace de verificación para activar la cuenta.
    
    Genera un token seguro si no existe uno activo, construye la URL absoluta
    y envía el correo tanto en formato HTML como en texto plano.
    """
    token = perfil.generar_token_verificacion()
    
    # Construir la URL absoluta de verificación
    path = reverse('usuarios:verificar_correo', kwargs={'token': token})
    if request:
        verification_url = request.build_absolute_uri(path)
    else:
        base_url = getattr(settings, 'APP_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
        verification_url = f"{base_url}{path}"

    asunto = "Global Exchange — Verificación y activación de tu cuenta"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@globalexchange.com')
    destinatario = [user.email]

    contexto = {
        'user': user,
        'perfil': perfil,
        'verification_url': verification_url,
        'expiration_hours': getattr(settings, 'EMAIL_TOKEN_EXPIRATION_HOURS', 24),
    }

    # Renderizar template HTML del email
    try:
        html_message = render_to_string('usuarios/emails/verificacion_email.html', contexto)
        plain_message = strip_tags(html_message)
    except Exception:
        # Fallback si el template aún no se carga
        plain_message = (
            f"Hola {user.first_name or user.username},\n\n"
            f"Gracias por registrarte en Global Exchange.\n"
            f"Para activar tu cuenta y comenzar a operar, haz clic en el siguiente enlace:\n\n"
            f"{verification_url}\n\n"
            f"Este enlace expirará en {getattr(settings, 'EMAIL_TOKEN_EXPIRATION_HOURS', 24)} horas.\n"
            f"Si no creaste esta cuenta, puedes ignorar este mensaje."
        )
        html_message = None

    # Envío a través de Django Mail
    try:
        send_mail(
            subject=asunto,
            message=plain_message,
            from_email=from_email,
            recipient_list=destinatario,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("Correo de activación enviado a %s para el usuario %s", user.email, user.username)
    except Exception as e:
        logger.error("Error al enviar correo de activación a %s: %s", user.email, e)

    # Intento opcional de disparar también vía Keycloak Admin API
    if perfil.keycloak_id and not perfil.keycloak_id.startswith('mock-'):
        try:
            kc_service = KeycloakAdminService()
            kc_service.enviar_correo_verificacion(perfil.keycloak_id)
        except Exception as e:
            logger.debug("Aviso: No se ejecutó el trigger secundario de Keycloak: %s", e)

    return verification_url
