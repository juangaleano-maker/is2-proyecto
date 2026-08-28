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
