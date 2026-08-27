from django.urls import path
from . import views

urlpatterns = [
    path('seleccionarCliente/', views.elegir_cliente, name='elegir_cliente'),
]

