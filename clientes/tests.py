from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from .models import Cliente


def crear_cliente(**kwargs):
    """Helper para crear clientes en tests."""
    defaults = {
        "tipo_persona": "FISICA",
        "documento": "123456",
        "nombre": "Juan",
        "apellido": "Pérez",
        "email": "juan@example.com",
        "segmento": "MINORISTA",
    }
    defaults.update(kwargs)
    return Cliente.objects.create(**defaults)


class DesactivarClienteTests(TestCase):

    def test_desactivar_pone_activo_en_false(self):
        """La baja lógica debe setear activo=False sin borrar el registro."""
        cliente = crear_cliente()
        self.assertTrue(cliente.activo)

        self.client.post(reverse("clientes:desactivar", args=[cliente.pk]))

        cliente.refresh_from_db()
        self.assertFalse(cliente.activo)
        # El registro sigue existiendo en la base de datos
        self.assertTrue(Cliente.objects.filter(pk=cliente.pk).exists())

    def test_desactivar_redirige_al_listado(self):
        """Tras desactivar, debe redirigir al listado."""
        cliente = crear_cliente()
        response = self.client.post(reverse("clientes:desactivar", args=[cliente.pk]))
        self.assertRedirects(response, reverse("clientes:listado"))

    def test_no_permite_desactivar_cliente_ya_inactivo(self):
        """Si el cliente ya está inactivo, redirige al detalle con advertencia."""
        cliente = crear_cliente(activo=False, documento="999999")
        response = self.client.post(reverse("clientes:desactivar", args=[cliente.pk]))
        self.assertRedirects(response, reverse("clientes:detalle", args=[cliente.pk]))

    def test_get_muestra_confirmacion(self):
        """GET a /desactivar/ debe mostrar la página de confirmación."""
        cliente = crear_cliente()
        response = self.client.get(reverse("clientes:desactivar", args=[cliente.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cliente.nombre)

    def test_listado_solo_muestra_activos_por_defecto(self):
        """El listado sin parámetros no debe incluir clientes inactivos."""
        crear_cliente(documento="111111")
        crear_cliente(documento="222222", activo=False)

        response = self.client.get(reverse("clientes:listado"))
        clientes = list(response.context["clientes"])
        self.assertTrue(all(c.activo for c in clientes))
        self.assertEqual(len(clientes), 1)

    def test_listado_con_ver_inactivos_muestra_todos(self):
        """Con ?ver_inactivos=1, el listado incluye tanto activos como inactivos."""
        crear_cliente(documento="111111")
        crear_cliente(documento="222222", activo=False)

        response = self.client.get(reverse("clientes:listado") + "?ver_inactivos=1")
        clientes = list(response.context["clientes"])
        self.assertEqual(len(clientes), 2)

    def test_no_permite_documento_duplicado(self):
        """No se puede registrar dos clientes con el mismo documento."""
        Cliente.objects.create(tipo_persona="FISICA", documento="123456", nombre="Juan", email="a@a.com")
        with self.assertRaises(Exception):
            Cliente.objects.create(tipo_persona="FISICA", documento="123456", nombre="Otro", email="b@b.com")