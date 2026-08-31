from django.urls import path
from . import views

urlpatterns = [
    path('agregarUsuario/', views.agregar_usuario, name='agregar_usuario'),
]
