from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect, render

from .decorators import rol_requerido


def login_view(request):
    """Punto de entrada: si ya está logueado va al menú, si no, muestra la pantalla de inicio con opciones de Login y Registro."""
    if request.user.is_authenticated:
        return redirect('menu')
    # Renderizamos una landing page en lugar de redirigir inmediatamente a Keycloak
    return render(request, 'authentication/landing.html')


from django.conf import settings

def logout_view(request):
    # Guardamos el token antes de destruir la sesión de Django
    id_token = request.session.get('oidc_id_token', '')
    django_logout(request)
    # Redirigir al endpoint de logout de Keycloak
    keycloak_logout = f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?client_id={settings.OIDC_RP_CLIENT_ID}"
    if id_token:
        # Con el id_token, Keycloak nos permite volver automáticamente sin dejar la pantalla gris
        redirect_uri = request.build_absolute_uri('/oidc/callback/')
        keycloak_logout += f"&post_logout_redirect_uri={redirect_uri}&id_token_hint={id_token}"
    return redirect(keycloak_logout)


def menu(request):
    """Menú principal post-login."""
    return render(request, 'authentication/menu.html', {
        'roles': sorted(request.roles),
    })


@rol_requerido('admin')
def solo_admin(request):
    """Vista de demo: solo accesible para quien tenga el rol admin asignado en Keycloak."""
    return render(request, 'authentication/menu.html', {
        'roles': sorted(request.roles),
        'mensaje': 'Estás viendo una sección exclusiva para el rol admin.',
    })
