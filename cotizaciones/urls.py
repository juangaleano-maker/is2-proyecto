from django.urls import path
from . import views

urlpatterns = [
    # Panel del Analista Cambiario
    path('panel/', views.analista_panel, name='analista_panel'),

    # Frontend HTML para registrar
    path('registrar/', views.cotizaciones_frontend, name='cotizaciones_registrar_frontend'),

    # API endpoints
    path('api/registrar/', views.registrar_cotizacion_api, name='api_registrar_cotizacion'),
]
