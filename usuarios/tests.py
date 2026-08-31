from datetime import timedelta
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ReenviarCorreoForm, RegistroUsuarioForm
from .models import EstadoUsuario, PerfilUsuario
from .services.email_service import enviar_correo_activacion
from .services.keycloak_service import KeycloakAdminService


class PerfilUsuarioModelTests(TestCase):
    """Pruebas unitarias para el modelo PerfilUsuario y manejo de estados."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Password123!',
            is_active=False
        )
        self.perfil = PerfilUsuario.objects.create(
            user=self.user,
            keycloak_id='kc-12345',
            estado=EstadoUsuario.PENDIENTE_VERIFICACION,
            email_verificado=False
        )

    def test_estado_inicial_pendiente(self):
        """Verifica que el usuario se crea con estado PENDIENTE_VERIFICACION e inactivo."""
        self.assertEqual(self.perfil.estado, EstadoUsuario.PENDIENTE_VERIFICACION)
        self.assertFalse(self.perfil.email_verificado)
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.perfil.esta_activo)

    def test_generacion_y_validacion_token(self):
        """Verifica la generación de token seguro y su validación temporal."""
        token = self.perfil.generar_token_verificacion()
        self.assertIsNotNone(token)
        self.assertTrue(len(token) >= 32)
        self.assertTrue(self.perfil.is_token_valido(token))
        self.assertFalse(self.perfil.is_token_valido('token-falso'))

    def test_token_expirado_es_invalido(self):
        """Verifica que un token vencido sea rechazado."""
        token = self.perfil.generar_token_verificacion()
        # Simular expiración colocando fecha en el pasado
        self.perfil.token_expiracion = timezone.now() - timedelta(minutes=1)
        self.perfil.save()
        self.assertFalse(self.perfil.is_token_valido(token))

    def test_activacion_de_cuenta(self):
        """Verifica que la activación cambie el estado a ACTIVO y active el User de Django."""
        self.perfil.generar_token_verificacion()
        self.perfil.activar_cuenta()

        self.perfil.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.perfil.estado, EstadoUsuario.ACTIVO)
        self.assertTrue(self.perfil.email_verificado)
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.perfil.esta_activo)
        self.assertIsNone(self.perfil.token_verificacion)


class RegistroFormTests(TestCase):
    """Pruebas de validación del formulario de autoregistro."""

    def test_formulario_valido(self):
        form = RegistroUsuarioForm(data={
            'username': 'nuevo_usuario',
            'email': 'nuevo@example.com',
            'first_name': 'Carlos',
            'last_name': 'Benítez',
            'password': 'Password123!',
            'password_confirm': 'Password123!'
        })
        self.assertTrue(form.is_valid())

    def test_password_inseguro_falla_rnf24(self):
        """Valida que contraseñas cortas o sin requisitos especiales sean rechazadas."""
        # Menos de 8 caracteres
        f1 = RegistroUsuarioForm(data={'password': 'Pass1!'})
        self.assertIn('password', f1.errors)

        # Sin mayúscula
        f2 = RegistroUsuarioForm(data={'password': 'password123!'})
        self.assertIn('password', f2.errors)

        # Sin número
        f3 = RegistroUsuarioForm(data={'password': 'Password!@#'})
        self.assertIn('password', f3.errors)

        # Sin carácter especial
        f4 = RegistroUsuarioForm(data={'password': 'Password1234'})
        self.assertIn('password', f4.errors)

    def test_password_mismatch(self):
        """Valida que las contraseñas que no coinciden generen error."""
        form = RegistroUsuarioForm(data={
            'username': 'usuario2',
            'email': 'u2@example.com',
            'first_name': 'Juan',
            'last_name': 'Pérez',
            'password': 'Password123!',
            'password_confirm': 'Diferente123!'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password_confirm', form.errors)

    def test_usuario_y_email_duplicados(self):
        """Valida que no se permitan usernames ni emails duplicados."""
        User.objects.create_user(username='existente', email='existente@example.com', password='Pass1234!#')

        form_user = RegistroUsuarioForm(data={
            'username': 'existente',
            'email': 'otro@example.com',
            'first_name': 'A',
            'last_name': 'B',
            'password': 'Password123!',
            'password_confirm': 'Password123!'
        })
        self.assertFalse(form_user.is_valid())
        self.assertIn('username', form_user.errors)

        form_email = RegistroUsuarioForm(data={
            'username': 'otro_user',
            'email': 'existente@example.com',
            'first_name': 'A',
            'last_name': 'B',
            'password': 'Password123!',
            'password_confirm': 'Password123!'
        })
        self.assertFalse(form_email.is_valid())
        self.assertIn('email', form_email.errors)


class EmailServiceTests(TestCase):
    """Pruebas del servicio de envío de correo de activación."""

    def test_envio_correo_generacion_token(self):
        user = User.objects.create_user(username='mailuser', email='mailuser@example.com', password='Pass1234!#')
        perfil = PerfilUsuario.objects.create(user=user)

        url = enviar_correo_activacion(user, perfil)

        self.assertIn(perfil.token_verificacion, url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['mailuser@example.com'])
        self.assertIn('Verificación', mail.outbox[0].subject)


class KeycloakServiceTests(TestCase):
    """Pruebas para el servicio de integración con la Admin API de Keycloak."""

    def test_modo_fallback_sin_keycloak(self):
        service = KeycloakAdminService()
        service.is_enabled = False
        res = service.crear_usuario(
            username='kcuser',
            email='kc@example.com',
            first_name='KC',
            last_name='User',
            password='Password123!'
        )
        self.assertTrue(res['success'])
        self.assertTrue(res['simulated'])
        self.assertTrue(res['keycloak_id'].startswith('mock-'))

    @patch('requests.post')
    def test_crear_usuario_keycloak_api_exitoso(self, mock_post):
        # Mock token request
        mock_post.return_value.status_code = 201
        mock_post.return_value.headers = {'Location': 'http://localhost:8080/admin/realms/global-exchange/users/kc-uuid-999'}

        service = KeycloakAdminService()
        with patch.object(service, 'get_admin_token', return_value='valid-token'):
            res = service.crear_usuario(
                username='kcuser2',
                email='kc2@example.com',
                first_name='KC2',
                last_name='User2',
                password='Password123!'
            )
            self.assertTrue(res['success'])
            self.assertEqual(res['keycloak_id'], 'kc-uuid-999')


class UsuariosViewsTests(TestCase):
    """Pruebas de vistas y flujo completo de registro y verificación."""

    def setUp(self):
        self.client = Client()

    def test_vista_registro_get(self):
        response = self.client.get(reverse('usuarios:registro'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Crear nueva cuenta')

    def test_flujo_autoregistro_completo(self):
        """Registro -> Estado Pendiente -> Verificación por correo -> Estado Activo."""
        # 1. Registrar
        post_data = {
            'username': 'mariag',
            'email': 'maria@example.com',
            'first_name': 'María',
            'last_name': 'González',
            'password': 'SecretPassword123!',
            'password_confirm': 'SecretPassword123!'
        }
        response = self.client.post(reverse('usuarios:registro'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verificar usuario creado
        user = User.objects.get(username='mariag')
        self.assertFalse(user.is_active)  # Inactivo antes de verificar
        perfil = user.perfil
        self.assertEqual(perfil.estado, EstadoUsuario.PENDIENTE_VERIFICACION)
        self.assertIsNotNone(perfil.token_verificacion)

        # 2. Verificar correo con el token
        token = perfil.token_verificacion
        verify_url = reverse('usuarios:verificar_correo', kwargs={'token': token})
        response_verify = self.client.get(verify_url)
        self.assertEqual(response_verify.status_code, 200)
        self.assertContains(response_verify, '¡Verificación Completada!')

        # 3. Comprobar que el usuario ahora está activo
        user.refresh_from_db()
        perfil.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(perfil.estado, EstadoUsuario.ACTIVO)
        self.assertTrue(perfil.email_verificado)

    def test_verificacion_token_invalido(self):
        verify_url = reverse('usuarios:verificar_correo', kwargs={'token': 'token-invalido-123'})
        response = self.client.get(verify_url)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'No se pudo verificar la cuenta', status_code=400)

    def test_reenviar_correo_verificacion(self):
        user = User.objects.create_user(username='reenvio_user', email='reenvio@example.com', is_active=False)
        perfil = PerfilUsuario.objects.create(user=user, estado=EstadoUsuario.PENDIENTE_VERIFICACION)

        response = self.client.post(reverse('usuarios:reenviar_correo'), {'email': 'reenvio@example.com'}, follow=True)
        self.assertEqual(response.status_code, 200)

        perfil.refresh_from_db()
        self.assertIsNotNone(perfil.token_verificacion)
        self.assertTrue(len(mail.outbox) >= 1)


class UsuariosAPITests(TestCase):
    """Pruebas de los endpoints API REST (JSON)."""

    def setUp(self):
        self.client = Client()

    def test_api_registro_exitoso(self):
        payload = {
            'username': 'api_user',
            'email': 'api_user@example.com',
            'first_name': 'Api',
            'last_name': 'Tester',
            'password': 'Password123!',
            'password_confirm': 'Password123!'
        }
        response = self.client.post(
            reverse('usuarios:api_registro'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['estado'], 'PENDIENTE_VERIFICACION')

    def test_api_verificar_correo(self):
        user = User.objects.create_user(username='api_verify', email='apiv@example.com', is_active=False)
        perfil = PerfilUsuario.objects.create(user=user, estado=EstadoUsuario.PENDIENTE_VERIFICACION)
        token = perfil.generar_token_verificacion()

        response = self.client.post(
            reverse('usuarios:api_verificar_correo'),
            data={'token': token},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['estado'], 'ACTIVO')
        self.assertTrue(data['data']['is_active'])

    def test_api_estado_usuario(self):
        user = User.objects.create_user(username='api_check', email='apic@example.com', is_active=True)
        PerfilUsuario.objects.create(user=user, estado=EstadoUsuario.ACTIVO, email_verificado=True)

        response = self.client.get(f"{reverse('usuarios:api_estado_usuario')}?q=api_check")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['estado'], 'ACTIVO')
        self.assertTrue(data['email_verificado'])


# Create your tests here.
