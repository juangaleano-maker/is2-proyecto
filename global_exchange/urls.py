"""
URL configuration for global_exchange project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='login', permanent=False)),
    path('admin/', admin.site.urls),
    path('auth/', include('usuarios.urls')),
    path('', lambda request: redirect('usuarios:registro'), name='root_redirect'),
    path('clientes/', include('clientes.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('agregar_usuario/', include('agregar_usuario.urls')),
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('', include('authentication.urls')),
]
