from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect, render


def login_view(request):
    """Punto de entrada: si ya está logueado va al menú, si no, dispara el login OIDC."""
    if request.user.is_authenticated:
        return redirect('menu')
    return redirect('oidc_authentication_init')


def logout_view(request):
    django_logout(request)
    return redirect('login')


def menu(request):
    """Menú principal post-login."""
    return render(request, 'authentication/menu.html', {
        'roles': sorted(request.roles),
    })
