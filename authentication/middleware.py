class RolesMiddleware:
    """
    Agrega `request.roles` (set de nombres de rol/grupo) a cada request,
    para poder chequear roles fácil en vistas/templates sin repetir la
    consulta a Group. No reemplaza a @rol_requerido: eso sigue siendo
    lo que bloquea el acceso; esto es solo comodidad.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.roles = set(request.user.groups.values_list('name', flat=True))
        else:
            request.roles = set()
        return self.get_response(request)

from django.shortcuts import redirect

class CanonicalHostMiddleware:
    """
    Si el usuario entra por 127.0.0.1, lo redirige a localhost
    para evitar el error de redirect_uri inválido en Keycloak.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host()
        if host.startswith('127.0.0.1'):
            # Reemplazar 127.0.0.1 por localhost en la URL
            new_url = request.build_absolute_uri().replace('127.0.0.1', 'localhost', 1)
            return redirect(new_url)
        return self.get_response(request)

class ClientSelectionMiddleware:
    """
    Fuerza a usuarios con múltiples clientes asignados a seleccionar uno 
    antes de poder realizar cualquier acción en el sistema.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Omitir validación en rutas estáticas, admin o de autenticación
        exempt_paths = ['/oidc/', '/logout/', '/admin/', '/clientes/seleccionarCliente/', '/static/', '/auth/', '/usuarios/']
        if any(request.path.startswith(p) for p in exempt_paths):
            return self.get_response(request)

        if request.user.is_authenticated:
            # Personal administrativo no necesita forzar la selección de cliente para navegar (pueden no tener cliente activo)
            roles = set(getattr(request, 'roles', []))
            roles_gestion = {'admin', 'supervisor', 'operador', 'empleado'}
            es_personal = bool(roles.intersection(roles_gestion))

            if not es_personal:
                cliente_activo_id = request.session.get('cliente_activo_id')
                if not cliente_activo_id:
                    user_email = request.user.email or request.user.username
                    
                    # Contar cuántos clientes activos tiene
                    from agregar_usuario.models import UsuarioCliente
                    from clientes.models import Cliente
                    from django.db import models

                    clientes_ids = UsuarioCliente.objects.filter(email__iexact=user_email).values_list('cliente_id', flat=True)
                    cantidad_clientes = Cliente.objects.filter(models.Q(id__in=clientes_ids) | models.Q(email__iexact=user_email), activo=True).count()

                    if cantidad_clientes > 1:
                        # Si tiene más de uno y no ha seleccionado ninguno, forzar
                        return redirect('clientes:elegir_cliente')

        return self.get_response(request)
