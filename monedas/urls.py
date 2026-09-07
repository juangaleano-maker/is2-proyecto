from django.urls import path
from . import views

app_name = 'monedas'

urlpatterns = [
    path('consultar/', views.consultar_monedas, name='consultar'),
    path('registrar/', views.registrar_moneda, name='registrar'),
    path('alternar-estado/<int:pk>/', views.alternar_estado_moneda, name='alternar_estado'),
    path('editar/<int:pk>/', views.editar_moneda, name='editar'),
]
