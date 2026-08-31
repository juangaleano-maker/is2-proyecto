from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

# Roles definidos en el realm de Keycloak (keycloak/realm-export.json)
ROLES_KEYCLOAK = ['admin', 'operador', 'supervisor', 'empleado', 'cliente']


def rol_requerido(*roles_permitidos):
    """
    Uso:
        @rol_requerido('admin', 'supervisor')
        def mi_vista(request):
            ...

    Requiere sesión iniciada (redirige a login si no) y que el usuario
    pertenezca a alguno de los grupos/roles indicados (sincronizados
    desde Keycloak, ver IS2-31). Si no cumple, 403.
    """
    def decorador(vista):
        @wraps(vista)
        @login_required
        def _envoltura(request, *args, **kwargs):
            if request.roles.intersection(roles_permitidos):
                return vista(request, *args, **kwargs)
            raise PermissionDenied('No tenés el rol necesario para acceder a esta sección.')
        return _envoltura
    return decorador
