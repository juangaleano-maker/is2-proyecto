from django.urls import path
from . import views

urlpatterns = [
    path('modificarUsuario/', views.listar_usuarios, name='listar_usuarios'),
    path('modificarUsuario/<int:usuario_id>/', views.modificar_usuario, name='modificar_usuario'),
]
