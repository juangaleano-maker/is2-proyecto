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
