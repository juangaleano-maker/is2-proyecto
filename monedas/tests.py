from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from .models import Moneda

User = get_user_model()

class MonedaTestCase(TestCase):
    def setUp(self):
        # Crear grupos de prueba
        self.admin_group = Group.objects.create(name='admin')
        self.cliente_group = Group.objects.create(name='cliente')

        # Crear usuarios
        self.admin_user = User.objects.create_user(username="testadmin", email="admin@test.com")
        self.admin_user.groups.add(self.admin_group)

        self.normal_user = User.objects.create_user(username="testuser", email="user@test.com")
        self.normal_user.groups.add(self.cliente_group)

        # Monedas de prueba iniciales
        self.moneda1 = Moneda.objects.create(nombre="Dólar", siglas="USD", activa=True)
        self.moneda2 = Moneda.objects.create(nombre="Euro", siglas="EUR", activa=True)
        self.moneda3 = Moneda.objects.create(nombre="Guaraní", siglas="PYG", activa=False)
        
        self.client = Client()

    def test_moneda_creation(self):
        """Verifica que los objetos Moneda se crean correctamente y su __str__"""
        self.assertEqual(Moneda.objects.count(), 3)
        self.assertEqual(str(self.moneda1), "Dólar (USD)")
        self.assertFalse(self.moneda3.activa)

    def test_consultar_monedas_view(self):
        """Verifica que la vista listar funciona y muestra las monedas."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('monedas:consultar'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dólar")
        self.assertContains(response, "USD")
        self.assertContains(response, "Guaraní")

    def test_consultar_monedas_filtro(self):
        """Verifica que la vista filtre correctamente por nombre mediante ?q="""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('monedas:consultar'), {'q': 'Euro'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Euro")
        self.assertNotContains(response, "Dólar")

    def test_registrar_moneda_exitoso(self):
        """Dado código y nombre, al confirmar, la moneda se guarda activa."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:registrar')
        data = {
            'nombre': 'Real Brasileño',
            'siglas': 'BRL',
        }
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse('monedas:consultar'))

        # Verificar que la moneda fue guardada activa
        moneda = Moneda.objects.get(siglas='BRL')
        self.assertEqual(moneda.nombre, 'Real Brasileño')
        self.assertTrue(moneda.activa)

    def test_registrar_moneda_codigo_duplicado(self):
        """Dado un código ya existente, muestra error de duplicado."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:registrar')
        data = {
            'nombre': 'Nuevo Dólar',
            'siglas': 'USD',  # Código ya registrado
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'siglas', 'Ya existe una moneda registrada con este código/siglas.')

    def test_registrar_moneda_campos_vacios(self):
        """Dado campos obligatorios vacíos, se muestran las validaciones correspondientes."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:registrar')
        data = {
            'nombre': '',
            'siglas': '',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'nombre', 'El nombre de la moneda es obligatorio.')
        self.assertFormError(response.context['form'], 'siglas', 'El código/siglas de la moneda es obligatorio.')

    def test_registrar_moneda_sin_permiso(self):
        """Un usuario que no sea admin no puede acceder a registrar moneda."""
        self.client.force_login(self.normal_user)
        url = reverse('monedas:registrar')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_desactivar_moneda_activa(self):
        """Dado que inactivo una moneda activa, su estado cambia a inactiva sin borrar el registro."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:alternar_estado', kwargs={'pk': self.moneda1.pk})
        response = self.client.post(url)

        self.assertRedirects(response, reverse('monedas:consultar'))
        self.moneda1.refresh_from_db()
        self.assertFalse(self.moneda1.activa)  # Verifica que está inactiva
        # Verificar que el registro sigue existiendo (historial preservado)
        self.assertTrue(Moneda.objects.filter(pk=self.moneda1.pk).exists())

    def test_activar_moneda_inactiva(self):
        """Dado una moneda inactiva, al alternar su estado vuelve a estar activa."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:alternar_estado', kwargs={'pk': self.moneda3.pk})
        response = self.client.post(url)

        self.assertRedirects(response, reverse('monedas:consultar'))
        self.moneda3.refresh_from_db()
        self.assertTrue(self.moneda3.activa)  # Verifica que ahora está activa

    def test_alternar_estado_sin_permiso(self):
        """Un usuario sin rol admin no puede desactivar monedas."""
        self.client.force_login(self.normal_user)
        url = reverse('monedas:alternar_estado', kwargs={'pk': self.moneda1.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)
        # Verificar que el estado NO cambió
        self.moneda1.refresh_from_db()
        self.assertTrue(self.moneda1.activa)

    def test_alternar_estado_moneda_inexistente(self):
        """Si la moneda no existe, debe devolver 404."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:alternar_estado', kwargs={'pk': 99999})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    # --- Pruebas para Modificar Moneda (IS2-41) ---

    def test_editar_moneda_sin_permiso(self):
        """Un usuario sin rol admin no puede editar monedas (403 Forbidden)."""
        self.client.force_login(self.normal_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        response_post = self.client.post(url, {'nombre': 'Hack Name', 'siglas': 'HCK'})
        self.assertEqual(response_post.status_code, 403)

    def test_editar_moneda_get_exitoso(self):
        """El administrador puede acceder al formulario de edición precargado."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Modificar Moneda')
        self.assertContains(response, self.moneda1.nombre)
        self.assertContains(response, self.moneda1.siglas)

    def test_editar_moneda_exitoso(self):
        """Dado que edito una moneda y guardo, los cambios se reflejan en la BD y en el listado."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})
        data = {
            'nombre': 'Dólar Estadounidense',
            'siglas': 'USD',
        }
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse('monedas:consultar'))

        self.moneda1.refresh_from_db()
        self.assertEqual(self.moneda1.nombre, 'Dólar Estadounidense')

        # Verificar que se refleja en el listado
        list_response = self.client.get(reverse('monedas:consultar'))
        self.assertContains(list_response, 'Dólar Estadounidense')

    def test_editar_moneda_mismos_datos_no_duplica(self):
        """Guardar una moneda conservando sus mismos datos no genera error de duplicado."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})
        data = {
            'nombre': self.moneda1.nombre,
            'siglas': self.moneda1.siglas,
        }
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse('monedas:consultar'))

    def test_editar_moneda_nombre_duplicado(self):
        """Intentar cambiar el nombre al de otra moneda ya existente genera error de validación."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})
        data = {
            'nombre': 'Euro',  # Ya pertenece a moneda2
            'siglas': 'USD',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'nombre', 'Ya existe una moneda registrada con este nombre.')

    def test_editar_moneda_siglas_duplicado(self):
        """Intentar cambiar las siglas a las de otra moneda ya existente genera error de validación."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})
        data = {
            'nombre': 'Dólar Americano',
            'siglas': 'EUR',  # Ya pertenece a moneda2
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'siglas', 'Ya existe una moneda registrada con este código/siglas.')

    def test_editar_moneda_campos_vacios(self):
        """Campos obligatorios vacíos al editar muestran error de validación."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})
        data = {
            'nombre': '',
            'siglas': '',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'nombre', 'El nombre de la moneda es obligatorio.')
        self.assertFormError(response.context['form'], 'siglas', 'El código/siglas de la moneda es obligatorio.')

    def test_editar_moneda_con_cotizaciones_requiere_confirmacion(self):
        """
        Dado que la moneda tiene cotizaciones asociadas, cuando intento modificarla
        sin confirmación explícita, el sistema lo impide y pide confirmación.
        """
        from unittest.mock import patch
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})

        with patch.object(Moneda, 'tiene_cotizaciones', return_value=True):
            # 1. GET muestra la advertencia
            response_get = self.client.get(url)
            self.assertEqual(response_get.status_code, 200)
            self.assertContains(response_get, 'Moneda con cotizaciones asociadas')
            self.assertContains(response_get, 'confirmar_modificacion')

            # 2. POST sin confirmación explícita es impedido
            response_post = self.client.post(url, {
                'nombre': 'Dólar Cambiado',
                'siglas': 'USD',
            })
            self.assertEqual(response_post.status_code, 200)
            self.moneda1.refresh_from_db()
            self.assertNotEqual(self.moneda1.nombre, 'Dólar Cambiado')
            self.assertContains(response_post, 'Esta moneda tiene cotizaciones asociadas')

    def test_editar_moneda_con_cotizaciones_confirmado_exitoso(self):
        """
        Dado que la moneda tiene cotizaciones asociadas, cuando se confirma
        explícitamente, los cambios se guardan exitosamente.
        """
        from unittest.mock import patch
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': self.moneda1.pk})

        with patch.object(Moneda, 'tiene_cotizaciones', return_value=True):
            response = self.client.post(url, {
                'nombre': 'Dólar Autorizado',
                'siglas': 'USD',
                'confirmar_modificacion': '1',
            })
            self.assertRedirects(response, reverse('monedas:consultar'))

            self.moneda1.refresh_from_db()
            self.assertEqual(self.moneda1.nombre, 'Dólar Autorizado')

    def test_editar_moneda_inexistente(self):
        """Intentar editar una moneda que no existe devuelve 404 Not Found."""
        self.client.force_login(self.admin_user)
        url = reverse('monedas:editar', kwargs={'pk': 88888})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
