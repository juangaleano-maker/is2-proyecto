from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect, render

from .decorators import rol_requerido


from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages


def login_view(request):
    """Punto de entrada: si ya está logueado va al menú, si no, muestra la pantalla de inicio con opciones de Login y Registro."""
    if request.user.is_authenticated:
        return redirect('menu')
    # Renderizamos una landing page en lugar de redirigir inmediatamente a Keycloak
    return render(request, 'authentication/landing.html')


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


@login_required
def menu(request):
    """
    Menú principal post-login.
    Carga el cliente activo en sesión (si existe) o el cliente vinculado al usuario.
    Si el usuario no es administrador/personal, no ve el panel de administración (/clientes, /clientes/nuevo),
    sino únicamente el Selector de Cliente Activo en Sesión y las opciones de consulta.
    """
    user_email = request.user.email or request.user.username
    cliente_activo = None

    # 1. Verificar si hay un cliente activo seleccionado en la sesión
    cliente_activo_id = request.session.get('cliente_activo_id')
    if cliente_activo_id:
        try:
            from clientes.models import Cliente
            cliente_activo = Cliente.objects.filter(id=cliente_activo_id, activo=True).first()
        except Exception:
            pass

    # 2. Si no hay en sesión, buscar si tiene un cliente asignado por email
    if not cliente_activo:
        try:
            from agregar_usuario.models import UsuarioCliente
            from clientes.models import Cliente
            from django.db import models
            
            clientes_ids = UsuarioCliente.objects.filter(email__iexact=user_email).values_list('cliente_id', flat=True)
            clientes_activos = Cliente.objects.filter(models.Q(id__in=clientes_ids) | models.Q(email__iexact=user_email), activo=True)
            
            if clientes_activos.count() == 1:
                cliente_activo = clientes_activos.first()
                request.session['cliente_activo_id'] = cliente_activo.id
                request.session['cliente_activo_nombre'] = str(cliente_activo)
        except Exception:
            pass

    roles = set(getattr(request, 'roles', []))
    roles_admin = {'admin', 'supervisor', 'operador'}
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado'}
    
    es_admin = bool(roles.intersection(roles_admin))
    es_personal = bool(roles.intersection(roles_gestion))
    tiene_cliente = cliente_activo is not None
    
    # Si no tiene cliente activo y no es del personal administrativo, solo puede hacer consultas
    solo_consulta = not tiene_cliente and not es_personal

    return render(request, 'authentication/menu.html', {
        'roles': sorted(roles),
        'cliente_activo': cliente_activo,
        'tiene_cliente': tiene_cliente,
        'es_admin': es_admin,
        'es_personal': es_personal,
        'solo_consulta': solo_consulta,
    })


@rol_requerido('admin')
def solo_admin(request):
    """Vista de demo: solo accesible para quien tenga el rol admin asignado en Keycloak."""
    return render(request, 'authentication/menu.html', {
        'roles': sorted(request.roles),
        'mensaje': 'Estás viendo una sección exclusiva para el rol admin.',
    })
