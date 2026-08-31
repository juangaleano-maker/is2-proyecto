from django.urls import path
from . import views

app_name = 'usuarios'

urlpatterns = [
    # Vistas Web de Autoregistro y Verificación
    path('registro/', views.RegistroView.as_view(), name='registro'),
    path('registro/exitoso/', views.RegistroExitosoView.as_view(), name='registro_exitoso'),
    path('verificar-correo/<str:token>/', views.VerificarCorreoView.as_view(), name='verificar_correo'),
    path('reenviar-verificacion/', views.ReenviarCorreoVerificacionView.as_view(), name='reenviar_correo'),
    path('estado-cuenta/', views.EstadoCuentaView.as_view(), name='estado_cuenta'),

    # Endpoints API REST (JSON)
    path('api/registro/', views.APIRegistroView.as_view(), name='api_registro'),
    path('api/verificar-correo/', views.APIVerificarCorreoView.as_view(), name='api_verificar_correo'),
    path('api/reenviar-verificacion/', views.APIReenviarVerificacionView.as_view(), name='api_reenviar_verificacion'),
    path('api/estado/', views.APIEstadoUsuarioView.as_view(), name='api_estado_usuario'),

    path('modificarUsuario/', views.listar_usuarios, name='listar_usuarios'),
    path('modificarUsuario/<int:usuario_id>/', views.modificar_usuario, name='modificar_usuario'),
]
