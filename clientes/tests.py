import json
from django.test import TestCase
from django.urls import reverse
from .models import Cliente


def crear_cliente(**kwargs):
    """Crea un cliente en BD saltando la validación del formulario (útil para setup de tests)."""
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


#  HU: Desactivar Cliente

class DesactivarClienteTests(TestCase):

    def test_desactivar_pone_activo_en_false(self):
        """La baja lógica debe setear activo=False sin borrar el registro."""
        cliente = crear_cliente()
        self.client.post(reverse("clientes:desactivar", args=[cliente.pk]))
        cliente.refresh_from_db()
        self.assertFalse(cliente.activo)
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


class ReactivarClienteTests(TestCase):

    def test_reactivar_pone_activo_en_true(self):
        """Reactivar un cliente inactivo debe setear activo=True."""
        cliente = crear_cliente(activo=False, documento="999999")
        response = self.client.post(reverse("clientes:reactivar", args=[cliente.pk]))
        cliente.refresh_from_db()
        self.assertTrue(cliente.activo)
        self.assertRedirects(response, reverse("clientes:detalle", args=[cliente.pk]))

    def test_no_permite_reactivar_cliente_ya_activo(self):
        """Si el cliente ya está activo, redirige al detalle con advertencia."""
        cliente = crear_cliente(activo=True)
        response = self.client.post(reverse("clientes:reactivar", args=[cliente.pk]))
        self.assertRedirects(response, reverse("clientes:detalle", args=[cliente.pk]))

    def test_get_muestra_confirmacion_reactivacion(self):
        """GET a /reactivar/ debe mostrar la página de confirmación."""
        cliente = crear_cliente(activo=False, documento="888888")
        response = self.client.get(reverse("clientes:reactivar", args=[cliente.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cliente.nombre)


class BusquedaFiltrosTests(TestCase):

    def test_busqueda_por_nombre(self):
        """Búsqueda con ?q= debe filtrar por nombre."""
        crear_cliente(nombre="Alejandro", documento="111111")
        crear_cliente(nombre="Beatriz", documento="222222")
        response = self.client.get(reverse("clientes:listado") + "?q=Alejandro")
        clientes = list(response.context["clientes"])
        self.assertEqual(len(clientes), 1)
        self.assertEqual(clientes[0].nombre, "Alejandro")

    def test_filtro_por_tipo_persona(self):
        """Filtro por ?tipo=JURIDICA debe devolver solo empresas."""
        crear_cliente(tipo_persona="FISICA", documento="111111")
        crear_cliente(tipo_persona="JURIDICA", razon_social="Tech SA", documento="RUC-22222")
        response = self.client.get(reverse("clientes:listado") + "?tipo=JURIDICA")
        clientes = list(response.context["clientes"])
        self.assertEqual(len(clientes), 1)
        self.assertEqual(clientes[0].razon_social, "Tech SA")

    def test_raiz_redirige_a_clientes(self):
        """GET / debe redirigir a /clientes/."""
        response = self.client.get("/")
        self.assertRedirects(response, reverse("clientes:listado"))


# ─────────────────────────────────────────────
#  HU: Modificar Cliente
# ─────────────────────────────────────────────

class ModificarClienteTests(TestCase):

    def test_editar_actualiza_datos(self):
        """POST con datos válidos debe actualizar el cliente en la BD."""
        cliente = crear_cliente()
        response = self.client.post(
            reverse("clientes:editar", args=[cliente.pk]),
            {
                "tipo_persona": "FISICA",
                "segmento": "VIP",
                "documento": "123456",
                "nombre": "Juan Modificado",
                "apellido": "Pérez",
                "email": "nuevo@example.com",
                "telefono": "",
                "direccion": "",
                "razon_social": "",
            }
        )
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, "Juan Modificado")
        self.assertEqual(cliente.segmento, "VIP")
        self.assertEqual(cliente.email, "nuevo@example.com")

    def test_editar_redirige_al_detalle(self):
        """Tras editar con éxito, debe redirigir al detalle del cliente."""
        cliente = crear_cliente()
        response = self.client.post(
            reverse("clientes:editar", args=[cliente.pk]),
            {
                "tipo_persona": "FISICA",
                "segmento": "MINORISTA",
                "documento": "123456",
                "nombre": "Juan",
                "apellido": "Pérez",
                "email": "juan@example.com",
                "telefono": "",
                "direccion": "",
                "razon_social": "",
            }
        )
        self.assertRedirects(response, reverse("clientes:detalle", args=[cliente.pk]))

    def test_editar_get_muestra_formulario_precargado(self):
        """GET a /editar/ debe mostrar el formulario con los datos actuales."""
        cliente = crear_cliente()
        response = self.client.get(reverse("clientes:editar", args=[cliente.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cliente.nombre)
        self.assertContains(response, cliente.documento)

    def test_no_permite_documento_duplicado_al_editar(self):
        """No se puede cambiar el documento de un cliente a uno que ya usa otro cliente."""
        crear_cliente(documento="111111")
        cliente2 = crear_cliente(documento="222222", nombre="Ana", apellido="López", email="ana@example.com")
        response = self.client.post(
            reverse("clientes:editar", args=[cliente2.pk]),
            {
                "tipo_persona": "FISICA",
                "segmento": "MINORISTA",
                "documento": "111111",
                "nombre": "Ana",
                "apellido": "López",
                "email": "ana@example.com",
                "telefono": "",
                "direccion": "",
                "razon_social": "",
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "documento",
                             "Ya existe un cliente registrado con este documento.")

    def test_permite_guardar_mismo_documento_propio(self):
        """Editar un cliente con su mismo documento no debe disparar error de duplicado."""
        cliente = crear_cliente()
        response = self.client.post(
            reverse("clientes:editar", args=[cliente.pk]),
            {
                "tipo_persona": "FISICA",
                "segmento": "CORPORATIVO",
                "documento": cliente.documento,
                "nombre": "Juan",
                "apellido": "Pérez",
                "email": "juan@example.com",
                "telefono": "",
                "direccion": "",
                "razon_social": "",
            }
        )
        self.assertRedirects(response, reverse("clientes:detalle", args=[cliente.pk]))


# ─────────────────────────────────────────────
#  Validaciones específicas por tipo
# ─────────────────────────────────────────────

class ValidacionesPorTipoTests(TestCase):

    def _post_form(self, data):
        return self.client.post(reverse("clientes:registrar"), data)

    def test_persona_fisica_sin_nombre_falla(self):
        """Persona física con nombre vacío debe mostrar error de validación."""
        response = self._post_form({
            "tipo_persona": "FISICA",
            "segmento": "MINORISTA",
            "documento": "123456",
            "nombre": "",
            "apellido": "Pérez",
            "email": "a@a.com",
            "telefono": "",
            "direccion": "",
            "razon_social": "",
        })
        self.assertEqual(response.status_code, 200)
        errores_nombre = response.context["form"].errors.get("nombre", [])
        self.assertIn("El nombre es obligatorio para persona física.", errores_nombre)

    def test_persona_fisica_sin_apellido_falla(self):
        """Persona física con apellido vacío debe mostrar error de validación."""
        response = self._post_form({
            "tipo_persona": "FISICA",
            "segmento": "MINORISTA",
            "documento": "123456",
            "nombre": "Juan",
            "apellido": "",
            "email": "a@a.com",
            "telefono": "",
            "direccion": "",
            "razon_social": "",
        })
        self.assertEqual(response.status_code, 200)
        errores_apellido = response.context["form"].errors.get("apellido", [])
        self.assertIn("El apellido es obligatorio para persona física.", errores_apellido)

    def test_persona_fisica_ci_con_letras_falla(self):
        """CI con letras debe disparar error de formato."""
        response = self._post_form({
            "tipo_persona": "FISICA",
            "segmento": "MINORISTA",
            "documento": "ABC123",
            "nombre": "Juan",
            "apellido": "Pérez",
            "email": "a@a.com",
            "telefono": "",
            "direccion": "",
            "razon_social": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "documento",
                             "La CI debe contener entre 6 y 8 dígitos numéricos (sin puntos ni guiones).")

    def test_persona_juridica_sin_razon_social_falla(self):
        """Persona jurídica sin razón social debe mostrar error."""
        response = self._post_form({
            "tipo_persona": "JURIDICA",
            "segmento": "CORPORATIVO",
            "documento": "RUC123456",
            "nombre": "",
            "apellido": "",
            "email": "empresa@a.com",
            "telefono": "",
            "direccion": "",
            "razon_social": "",
        })
        self.assertEqual(response.status_code, 200)
        errores_rs = response.context["form"].errors.get("razon_social", [])
        self.assertIn("La razón social es obligatoria para persona jurídica.", errores_rs)

    def test_persona_juridica_valida_se_guarda(self):
        """Persona jurídica completa y válida debe guardarse correctamente."""
        response = self._post_form({
            "tipo_persona": "JURIDICA",
            "segmento": "CORPORATIVO",
            "documento": "RUC-12345",
            "nombre": "",
            "apellido": "",
            "email": "empresa@a.com",
            "telefono": "099000000",
            "direccion": "Av. Principal 123",
            "razon_social": "Acme S.A.",
        })
        self.assertRedirects(response, reverse("clientes:listado"))
        self.assertTrue(Cliente.objects.filter(razon_social="Acme S.A.").exists())

    def test_no_permite_documento_duplicado(self):
        """No se puede registrar dos clientes con el mismo documento."""
        Cliente.objects.create(tipo_persona="FISICA", documento="123456",
                               nombre="Juan", apellido="X", email="a@a.com")
        with self.assertRaises(Exception):
            Cliente.objects.create(tipo_persona="FISICA", documento="123456",
                                   nombre="Otro", apellido="Y", email="b@b.com")


#  API REST

class ApiClientesTests(TestCase):

    def test_api_get_listado_retorna_200_json(self):
        """GET /clientes/api/ debe responder 200 con JSON."""
        crear_cliente()
        response = self.client.get(reverse("clientes:api_listado"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("clientes", data)
        self.assertEqual(len(data["clientes"]), 1)

    def test_api_get_excluye_inactivos_por_defecto(self):
        """La API no debe devolver clientes inactivos a menos que se pida."""
        crear_cliente(documento="111111")
        crear_cliente(documento="222222", activo=False)
        response = self.client.get(reverse("clientes:api_listado"))
        data = json.loads(response.content)
        self.assertEqual(len(data["clientes"]), 1)

    def test_api_post_crea_cliente(self):
        """POST /clientes/api/ con datos válidos debe crear el cliente y devolver 201."""
        payload = {
            "tipo_persona": "FISICA",
            "segmento": "MINORISTA",
            "documento": "654321",
            "nombre": "María",
            "apellido": "García",
            "email": "maria@example.com",
            "telefono": "",
            "direccion": "",
            "razon_social": "",
        }
        response = self.client.post(
            reverse("clientes:api_listado"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Cliente.objects.filter(documento="654321").exists())

    def test_api_post_datos_invalidos_retorna_400(self):
        """POST con datos inválidos debe retornar 400 con errores."""
        payload = {"tipo_persona": "FISICA", "documento": "ABC", "email": "no-es-email"}
        response = self.client.post(
            reverse("clientes:api_listado"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("errores", data)

    def test_api_get_detalle_retorna_cliente(self):
        """GET /clientes/api/<pk>/ debe devolver los datos del cliente."""
        cliente = crear_cliente()
        response = self.client.get(reverse("clientes:api_detalle", args=[cliente.pk]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["documento"], cliente.documento)
        self.assertEqual(data["nombre"], cliente.nombre)

    def test_api_put_modifica_cliente(self):
        """PUT /clientes/api/<pk>/ debe actualizar los datos del cliente."""
        cliente = crear_cliente()
        payload = {
            "tipo_persona": "FISICA",
            "segmento": "VIP",
            "documento": "123456",
            "nombre": "Juan Editado",
            "apellido": "Pérez",
            "email": "editado@example.com",
            "telefono": "",
            "direccion": "",
            "razon_social": "",
        }
        response = self.client.put(
            reverse("clientes:api_detalle", args=[cliente.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, "Juan Editado")
        self.assertEqual(cliente.segmento, "VIP")

    def test_api_delete_desactiva_cliente(self):
        """DELETE /clientes/api/<pk>/ debe hacer baja lógica."""
        cliente = crear_cliente()
        response = self.client.delete(reverse("clientes:api_detalle", args=[cliente.pk]))
        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertFalse(cliente.activo)
        self.assertTrue(Cliente.objects.filter(pk=cliente.pk).exists())

    def test_api_delete_cliente_ya_inactivo_retorna_400(self):
        """DELETE sobre cliente ya inactivo debe retornar 400."""
        cliente = crear_cliente(activo=False, documento="999999")
        response = self.client.delete(reverse("clientes:api_detalle", args=[cliente.pk]))
        self.assertEqual(response.status_code, 400)

    def test_api_filtro_por_segmento(self):
        """?segmento=VIP debe retornar solo los clientes VIP."""
        crear_cliente(documento="111111", segmento="MINORISTA")
        crear_cliente(documento="222222", segmento="VIP", nombre="Ana",
                      apellido="López", email="ana@example.com")
        response = self.client.get(reverse("clientes:api_listado") + "?segmento=VIP")
        data = json.loads(response.content)
        self.assertEqual(len(data["clientes"]), 1)
        self.assertEqual(data["clientes"][0]["segmento"], "VIP")