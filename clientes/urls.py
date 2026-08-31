from django.urls import path
from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.listado_clientes, name="listado"),
    path("panel/", views.listado_clientes, name="panel"),
    path("nuevo/", views.registrar_cliente, name="registrar"),
    path("<int:pk>/", views.detalle_cliente, name="detalle"),
    path("<int:pk>/editar/", views.editar_cliente, name="editar"),
    path("<int:pk>/desactivar/", views.desactivar_cliente, name="desactivar"),
    path("<int:pk>/reactivar/", views.reactivar_cliente, name="reactivar"),
    path("api/", views.api_clientes, name="api_listado"),
    path("api/<int:pk>/", views.api_cliente_detalle, name="api_detalle"),
    path('seleccionarCliente/', views.elegir_cliente, name='elegir_cliente'),
    path('consultarClienteAsignado/<int:cliente_id>/', views.consultar_cliente, name='consultar_cliente'),
]
