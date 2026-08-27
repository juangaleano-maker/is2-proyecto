from django.urls import path
from . import views

urlpatterns = [
    path('', views.elegir_cliente, name='elegir_cliente'),
    path('consultar/<int:cliente_id>/', views.consultar_cliente, name='consultar_cliente'),
]
