from django.urls import path
from . import views

urlpatterns = [
    path('seleccionarCliente/', views.elegir_cliente, name='elegir_cliente'),
    path('consultarClienteAsignado/<int:cliente_id>/', views.consultar_cliente, name='consultar_cliente'),
]
