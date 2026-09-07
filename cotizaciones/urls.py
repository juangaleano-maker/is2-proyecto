from django.urls import path
from . import views

urlpatterns = [
    # Panel del Analista Cambiario
    path('panel/', views.analista_panel, name='analista_panel'),

    # Frontend HTML para registrar
    path('registrar/', views.cotizaciones_frontend, name='cotizaciones_registrar_frontend'),

    # API endpoints
    path('api/registrar/', views.registrar_cotizacion_api, name='api_registrar_cotizacion'),

    # Simulador de conversión de moneda (IS2-10)
    path('simulador/', views.simulador_conversion_view, name='simulador_conversion'),
    path('api/simular/', views.api_simular_conversion, name='api_simular_conversion'),
]

