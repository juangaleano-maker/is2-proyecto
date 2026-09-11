from django.urls import path
from . import views

urlpatterns = [
    # Panel del analista
    path('panel/', views.analista_panel, name='analista_panel'),
    path('consultar/', views.consultar_cotizaciones, name='cotizaciones_consultar'),

    # Frontend HTML para registrar
    path('registrar/', views.cotizaciones_frontend, name='cotizaciones_registrar_frontend'),
    path('modificar/<int:cotizacion_id>/', views.cotizaciones_modificar_frontend, name='cotizaciones_modificar_frontend'),

    # Consulta de tasas de cambio vigentes para usuarios registrados (IS2-6 / IS2-7)
    path('tasas-vigentes/', views.consultar_tasas_vigentes, name='tasas_vigentes'),
    path('api/tasas-vigentes/', views.listar_tasas_vigentes_api, name='api_tasas_vigentes'),

    # Historial y evolución de tasas con descarga de reportes para usuarios registrados (IS2-8)
    path('historial/', views.historial_tasas, name='historial_tasas'),
    path('historial/descargar/', views.descargar_reporte_historial, name='descargar_reporte_historial'),

    # Vista pública para visitantes (IS2-20)
    path('visitante/', views.tasas_visitante, name='tasas_visitante'),

    # API endpoints
    path('api/registrar/', views.registrar_cotizacion_api, name='api_registrar_cotizacion'),
    path('api/modificar/<int:cotizacion_id>/', views.modificar_cotizacion_api, name='api_modificar_cotizacion'),
    path('api/desactivar/<int:cotizacion_id>/', views.desactivar_cotizacion_api, name='api_desactivar_cotizacion'),
    path('api/vigente/<str:origen>/<str:destino>/', views.obtener_tasa_vigente_api, name='api_obtener_tasa_vigente'),

    # Simulador de conversión de moneda (IS2-10)
    path('simulador/', views.simulador_conversion_view, name='simulador_conversion'),
    path('api/simular/', views.api_simular_conversion, name='api_simular_conversion'),
]
