
from django.urls import path
from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.listado_clientes, name="listado"),
    path("nuevo/", views.registrar_cliente, name="registrar"),
    path("<int:pk>/", views.detalle_cliente, name="detalle"),
    path("<int:pk>/editar/", views.editar_cliente, name="editar"),
    path("<int:pk>/eliminar/", views.eliminar_cliente, name="eliminar"),
]