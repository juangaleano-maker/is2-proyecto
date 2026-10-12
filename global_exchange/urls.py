"""
URL configuration for global_exchange project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:

Function views::
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views::
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf::
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from django.views.generic import RedirectView
from authentication import views as authentication_views
from cotizaciones import views as caja_views

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='login', permanent=False)),
    path('admin/', admin.site.urls),
    path('auth/', include('usuarios.urls')),
    path('', lambda request: redirect('usuarios:registro'), name='root_redirect'),
    path('clientes/', include('clientes.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('agregar_usuario/', include('agregar_usuario.urls')),
    path('cotizaciones/', include('cotizaciones.urls')),
    path('oidc/callback/', authentication_views.CustomOIDCAuthenticationCallbackView.as_view(), name='oidc_authentication_callback'),
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('', include('authentication.urls')),
    path('monedas/', include('monedas.urls')),
    path('pagos/', include('pagos.urls')),

    # Apertura y Cierre de Caja (IS2-60) y Movimientos (IS2-61) — rutas bajo /caja/
    path('caja/apertura/',    caja_views.apertura_caja_view,         name='apertura_caja'),
    path('caja/estado/',      caja_views.caja_dashboard_view,        name='caja_dashboard'),
    path('caja/cierre/',      caja_views.cierre_caja_view,           name='cierre_caja'),
    path('caja/movimientos/', caja_views.historial_movimientos_view, name='historial_movimientos'),
]

