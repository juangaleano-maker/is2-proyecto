from django.test import TestCase, Client
from django.urls import reverse

class EndpointTests(TestCase):
    def setUp(self):
        # Inicializa el cliente de pruebas de Django
        self.client = Client()
        # Aquí puedes crear datos de prueba en la base de datos si los endpoints lo requieren,
        # por ejemplo, crear un usuario o un cliente.

    def test_seleccionar_cliente(self):
        """Prueba que el endpoint /seleccionarCliente devuelva una respuesta exitosa."""
        response = self.client.get('/seleccionarCliente/')
        # Verifica que la respuesta sea 200 OK (o el código que esperes, ej. 302 si hay redirección)
        self.assertEqual(response.status_code, 200)

    def test_consultar_cliente_asignado(self):
        """Prueba que el endpoint /consultarClienteAsignado devuelva una respuesta exitosa."""
        response = self.client.get('/consultarClienteAsignado/')
        self.assertEqual(response.status_code, 200)

    def test_agregar_usuario(self):
        """Prueba que el endpoint /agregarUsuario funcione correctamente."""
        # Prueba GET para cargar el formulario
        response = self.client.get('/agregarUsuario/')
        self.assertEqual(response.status_code, 200)
        
        # Ejemplo de prueba POST (debes ajustar los datos según tu formulario)
        # data = {'nombre': 'Test', 'email': 'test@test.com', ...}
        # response = self.client.post('/agregarUsuario/', data)
        # self.assertEqual(response.status_code, 302) # si redirige al terminar

    def test_modificar_usuario_listado(self):
        """Prueba el listado o página general de modificar usuario /modificarUsuario/."""
        response = self.client.get('/modificarUsuario/')
        self.assertEqual(response.status_code, 200)

    def test_modificar_usuario_especifico(self):
        """Prueba modificar un usuario específico /modificarUsuario/<int:usuario_id>/."""
        # Reemplaza '1' por el ID de un usuario de prueba que hayas creado en setUp
        usuario_id_prueba = 1 
        url = f'/modificarUsuario/{usuario_id_prueba}/'
        
        # Prueba GET
        response = self.client.get(url)
        # Asumiendo que el ID 1 no existe en la BD vacía de prueba, podría dar 404.
        # Ajusta el código de estado esperado a tu lógica (ej. 200 si existe).
        self.assertIn(response.status_code, [200, 302, 404])
