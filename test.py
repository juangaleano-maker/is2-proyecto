from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from clientes.models import Cliente
from usuarios.models import Usuario

class EndpointTests(TestCase):
    def setUp(self):
        # Inicializa el cliente de pruebas de Django
        self.client = Client()

        # Cliente de prueba para consultar
        self.cliente = Cliente.objects.create(
            tipo_persona="FISICA",
            documento="12345678",
            nombre="Juan",
            apellido="Pérez",
            email="juan@example.com",
            segmento="MINORISTA"
        )

        # Usuario de prueba para modificar (obtenido de los creados por migración o creado)
        self.usuario = Usuario.objects.first()
        if not self.usuario:
            self.usuario = Usuario.objects.create(
                nombre="Carlos",
                apellido="Gómez",
                email="carlos.test@example.com",
                telefono="123456789",
                rol="Empleado"
            )

        # Usuario autenticado con rol admin para vistas protegidas
        self.admin_user, _ = User.objects.get_or_create(
            username='admin_test',
            defaults={'email': 'admin@example.com'}
        )
        self.admin_user.set_password('password123')
        self.admin_user.save()

        grupo_admin, _ = Group.objects.get_or_create(name='admin')
        self.admin_user.groups.add(grupo_admin)

    def test_seleccionar_cliente(self):
        """Prueba que el endpoint /clientes/seleccionarCliente/ devuelva una respuesta exitosa."""
        self.client.force_login(self.admin_user)
        response = self.client.get('/clientes/seleccionarCliente/')
        self.assertEqual(response.status_code, 200)

    def test_consultar_cliente_asignado(self):
        """Prueba que el endpoint /clientes/consultarClienteAsignado/<id>/ devuelva una respuesta exitosa."""
        self.client.force_login(self.admin_user)
        response = self.client.get(f'/clientes/consultarClienteAsignado/{self.cliente.id}/')
        self.assertEqual(response.status_code, 200)

    def test_agregar_usuario(self):
        """Prueba que el endpoint /agregar_usuario/agregarUsuario/ funcione correctamente."""
        self.client.force_login(self.admin_user)
        response = self.client.get('/agregar_usuario/agregarUsuario/')
        self.assertEqual(response.status_code, 200)

    def test_modificar_usuario_listado(self):
        """Prueba el listado o página general de modificar usuario /usuarios/modificarUsuario/."""
        self.client.force_login(self.admin_user)
        response = self.client.get('/usuarios/modificarUsuario/')
        self.assertEqual(response.status_code, 200)

    def test_modificar_usuario_especifico(self):
        """Prueba modificar un usuario específico /usuarios/modificarUsuario/<int:usuario_id>/."""
        self.client.force_login(self.admin_user)
        url = f'/usuarios/modificarUsuario/{self.usuario.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
