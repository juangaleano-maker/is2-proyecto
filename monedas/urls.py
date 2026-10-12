from django.urls import path
from . import views

app_name = 'monedas'

urlpatterns = [
    path('consultar/', views.consultar_monedas, name='consultar'),
    path('registrar/', views.registrar_moneda, name='registrar'),
    path('alternar-estado/<int:pk>/', views.alternar_estado_moneda, name='alternar_estado'),
    path('editar/<int:pk>/', views.editar_moneda, name='editar'),
    path('<int:moneda_id>/billetes/', views.gestionar_denominaciones_moneda, name='gestionar_billetes'),
    path('billetes/alternar/<int:pk>/', views.alternar_estado_denominacion, name='alternar_billete'),
    path('billetes/eliminar/<int:pk>/', views.eliminar_denominacion, name='eliminar_billete'),
]
