from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from decimal import Decimal
import time

from monedas.models import Moneda
from cotizaciones.models import Cotizacion

User = get_user_model()

class ConsultarTasasDeCambioTestCase(TestCase):
    """
    Pruebas unitarias para las Historias de Usuario IS2-6 e IS2-7:
    'Consultar tasas de cambio vigentes' para Usuario Registrado.
    """

    def setUp(self):
        # 1. Crear grupos de negocio
        self.grupo_cliente = Group.objects.create(name='cliente')
        self.grupo_operador = Group.objects.create(name='operador')

        # 2. Crear usuarios registrados
        self.usuario_cliente = User.objects.create_user(
            username='cliente_juan',
            email='juan@exchange.com',
            password='password123'
        )
        self.usuario_cliente.groups.add(self.grupo_cliente)

        self.usuario_operador = User.objects.create_user(
            username='operador_ana',
            email='ana@exchange.com',
            password='password123'
        )
        self.usuario_operador.groups.add(self.grupo_operador)

        # 3. Monedas disponibles
        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)
        self.eur = Moneda.objects.create(nombre='Euro', siglas='EUR', activa=True)
        self.brl_inactiva = Moneda.objects.create(nombre='Real Brasileño', siglas='BRL', activa=False)

        # 4. Crear cotizaciones históricas y vigentes
        # Par USD -> PYG: Antigua
        self.cot_usd_pyg_antigua = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7800.00'),
            venta=Decimal('7850.00'),
            activo=False,
            registrado_por=self.usuario_operador
        )

        # Par USD -> PYG: Vigente (más reciente)
        self.cot_usd_pyg_vigente = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7920.00'),
            venta=Decimal('7980.00'),
            activo=True,
            registrado_por=self.usuario_operador
        )

        # Par EUR -> PYG: Vigente
        self.cot_eur_pyg_vigente = Cotizacion.objects.create(
            moneda_origen=self.eur,
            moneda_destino=self.pyg,
            compra=Decimal('8400.00'),
            venta=Decimal('8500.00'),
            activo=True,
            registrado_por=self.usuario_operador
        )

        # Par con moneda inactiva (BRL -> PYG): No debe mostrarse
        self.cot_brl_inactiva = Cotizacion.objects.create(
            moneda_origen=self.brl_inactiva,
            moneda_destino=self.pyg,
            compra=Decimal('1350.00'),
            venta=Decimal('1400.00'),
            activo=True,
            registrado_por=self.usuario_operador
        )

        self.client = Client()

    def test_acceso_requiere_login_usuario_no_autenticado_redirige(self):
        """Un visitante anónimo no registrado debe ser redirigido al login."""
        response = self.client.get(reverse('tasas_vigentes'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_usuario_registrado_puede_consultar_sin_repetir_login(self):
        """
        Criterio 3: El usuario registrado debe poder consultar las tasas 
        con su sesión iniciada sin repetir el login en cada consulta.
        """
        self.client.force_login(self.usuario_cliente)

        # Primera consulta
        response1 = self.client.get(reverse('tasas_vigentes'))
        self.assertEqual(response1.status_code, 200)

        # Segunda consulta consecutiva (simulando refresco o navegación)
        response2 = self.client.get(reverse('tasas_vigentes'))
        self.assertEqual(response2.status_code, 200)
        self.assertContains(response2, "Tasas de Cambio Vigentes")

    def test_muestra_tasa_compra_y_venta_de_cada_moneda_disponible(self):
        """
        Criterio 1: El sistema debe mostrar la tasa de compra y venta de cada moneda disponible.
        """
        self.client.force_login(self.usuario_cliente)
        response = self.client.get(reverse('tasas_vigentes'))

        self.assertEqual(response.status_code, 200)
        # Verifica visualización de monedas disponibles
        self.assertContains(response, "USD")
        self.assertContains(response, "PYG")
        self.assertContains(response, "EUR")

        # Verifica tasas de compra y venta vigentes
        self.assertContains(response, "7920.00")  # Compra USD
        self.assertContains(response, "7980.00")  # Venta USD
        self.assertContains(response, "8400.00")  # Compra EUR
        self.assertContains(response, "8500.00")  # Venta EUR

        # Verifica que monedas inactivas no se muestran
        self.assertNotContains(response, "BRL")

    def test_tasas_reflejan_informacion_mas_reciente(self):
        """
        Criterio 2: Las tasas deben reflejar la información más reciente 
        obtenida de la fuente configurada (excluyendo valores históricos o desactualizados).
        """
        self.client.force_login(self.usuario_cliente)
        response = self.client.get(reverse('tasas_vigentes'))

        self.assertEqual(response.status_code, 200)
        # La tasa vigente más reciente para USD->PYG es 7920.00 / 7980.00
        self.assertContains(response, "7920.00")
        self.assertContains(response, "7980.00")

        # La tasa antigua (7800.00 / 7850.00) no debe aparecer como tasa vigente en las tarjetas
        tasas_en_contexto = response.context['tasas']
        cotizaciones_usd = [t for t in tasas_en_contexto if t.moneda_origen == self.usd and t.moneda_destino == self.pyg]
        self.assertEqual(len(cotizaciones_usd), 1)
        self.assertEqual(cotizaciones_usd[0].compra, Decimal('7920.00'))
        self.assertEqual(cotizaciones_usd[0].venta, Decimal('7980.00'))

    def test_actualizacion_de_tasa_refleja_inmediatamente_el_nuevo_valor(self):
        """
        Al registrar una nueva cotización activa para un par existente,
        la consulta debe reflejar de inmediato la nueva tasa.
        """
        self.client.force_login(self.usuario_cliente)

        # Crear una actualización de tasa para USD -> PYG
        nueva_cot = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('8000.00'),
            venta=Decimal('8050.00'),
            activo=True,
            registrado_por=self.usuario_operador
        )

        response = self.client.get(reverse('tasas_vigentes'))
        self.assertEqual(response.status_code, 200)

        # El valor nuevo debe estar presente
        self.assertContains(response, "8000.00")
        self.assertContains(response, "8050.00")

        # El par USD->PYG en contexto debe ser la nueva
        tasas = response.context['tasas']
        cot_usd = [t for t in tasas if t.moneda_origen == self.usd and t.moneda_destino == self.pyg][0]
        self.assertEqual(cot_usd.compra, Decimal('8000.00'))

    def test_filtro_por_moneda_origen(self):
        """Permite filtrar tasas por moneda de origen."""
        self.client.force_login(self.usuario_cliente)
        response = self.client.get(reverse('tasas_vigentes'), {'moneda_origen': 'USD'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['tasas']), 1)
        self.assertEqual(response.context['tasas'][0].moneda_origen.siglas, 'USD')

    def test_filtro_por_busqueda_general(self):
        """Permite buscar tasas por nombre o sigla de divisa."""
        self.client.force_login(self.usuario_cliente)
        response = self.client.get(reverse('tasas_vigentes'), {'q': 'Euro'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['tasas']), 1)
        self.assertEqual(response.context['tasas'][0].moneda_origen.siglas, 'EUR')

    def test_api_tasas_vigentes_endpoint(self):
        """El endpoint JSON devuelve las tasas vigentes estructuradas para usuarios registrados."""
        self.client.force_login(self.usuario_cliente)
        response = self.client.get(reverse('api_tasas_vigentes'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('tasas', data)
        self.assertEqual(data['total'], 2)  # USD->PYG y EUR->PYG

        pares = [(t['moneda_origen'], t['moneda_destino']) for t in data['tasas']]
        self.assertIn(('USD', 'PYG'), pares)
        self.assertIn(('EUR', 'PYG'), pares)


class HistorialTasasTestCase(TestCase):
    """
    Pruebas unitarias para la Historia de Usuario IS2-8:
    'Ver historial de tasas' y descarga de reportes para Usuario Registrado.
    """

    def setUp(self):
        from datetime import datetime, timedelta
        from django.utils import timezone

        self.grupo_cliente = Group.objects.create(name='cliente')
        self.usuario = User.objects.create_user(
            username='carlos_cliente',
            email='carlos@exchange.com',
            password='password123'
        )
        self.usuario.groups.add(self.grupo_cliente)

        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)
        self.eur = Moneda.objects.create(nombre='Euro', siglas='EUR', activa=True)

        self.hoy = timezone.now()
        self.hace_5_dias = self.hoy - timedelta(days=5)
        self.hace_15_dias = self.hoy - timedelta(days=15)
        self.hace_45_dias = self.hoy - timedelta(days=45)

        # Crear cotizaciones en diferentes fechas
        # Registro 1: Hace 45 días
        self.cot1 = Cotizacion.objects.create(
            moneda_origen=self.usd, moneda_destino=self.pyg,
            compra=Decimal('7600.00'), venta=Decimal('7650.00'),
            activo=False, registrado_por=self.usuario
        )
        Cotizacion.objects.filter(id=self.cot1.id).update(fecha=self.hace_45_dias)

        # Registro 2: Hace 15 días
        self.cot2 = Cotizacion.objects.create(
            moneda_origen=self.usd, moneda_destino=self.pyg,
            compra=Decimal('7750.00'), venta=Decimal('7800.00'),
            activo=False, registrado_por=self.usuario
        )
        Cotizacion.objects.filter(id=self.cot2.id).update(fecha=self.hace_15_dias)

        # Registro 3: Hace 5 días
        self.cot3 = Cotizacion.objects.create(
            moneda_origen=self.usd, moneda_destino=self.pyg,
            compra=Decimal('7880.00'), venta=Decimal('7930.00'),
            activo=False, registrado_por=self.usuario
        )
        Cotizacion.objects.filter(id=self.cot3.id).update(fecha=self.hace_5_dias)

        # Registro 4: Hoy (vigente)
        self.cot4 = Cotizacion.objects.create(
            moneda_origen=self.usd, moneda_destino=self.pyg,
            compra=Decimal('7950.00'), venta=Decimal('8000.00'),
            activo=True, registrado_por=self.usuario
        )

        # Registro EUR: Hoy
        self.cot_eur = Cotizacion.objects.create(
            moneda_origen=self.eur, moneda_destino=self.pyg,
            compra=Decimal('8500.00'), venta=Decimal('8600.00'),
            activo=True, registrado_por=self.usuario
        )

        self.client = Client()

    def test_historial_requiere_login(self):
        """Un usuario no autenticado no puede acceder al historial de tasas."""
        response = self.client.get(reverse('historial_tasas'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_usuario_registrado_accede_al_historial(self):
        """Un usuario registrado accede correctamente a la vista de historial."""
        self.client.force_login(self.usuario)
        response = self.client.get(reverse('historial_tasas'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historial y Evolución de Tasas de Cambio")

    def test_criterio_1_seleccion_rango_fechas(self):
        """
        Criterio 1: El sistema debe permitir seleccionar un rango de fechas.
        Filtrar entre hace 20 días y hace 2 días debe incluir solo las cotizaciones 2 y 3.
        """
        from datetime import timedelta
        self.client.force_login(self.usuario)

        desde = (self.hoy - timedelta(days=20)).strftime('%Y-%m-%d')
        hasta = (self.hoy - timedelta(days=2)).strftime('%Y-%m-%d')

        response = self.client.get(reverse('historial_tasas'), {
            'fecha_desde': desde,
            'fecha_hasta': hasta,
            'moneda_origen': 'USD',
        })

        self.assertEqual(response.status_code, 200)
        cotizaciones = response.context['cotizaciones']
        ids = [c.id for c in cotizaciones]

        # Debe incluir cot2 (hace 15 días) y cot3 (hace 5 días)
        self.assertIn(self.cot2.id, ids)
        self.assertIn(self.cot3.id, ids)
        # NO debe incluir cot1 (hace 45 días) ni cot4 (hoy)
        self.assertNotIn(self.cot1.id, ids)
        self.assertNotIn(self.cot4.id, ids)

    def test_criterio_2_muestra_tasa_correspondiente_a_cada_fecha(self):
        """
        Criterio 2: Debe mostrarse la tasa correspondiente a cada fecha consultada.
        """
        self.client.force_login(self.usuario)
        response = self.client.get(reverse('historial_tasas'), {'moneda_origen': 'USD'})

        self.assertEqual(response.status_code, 200)
        # Verifica que aparecen los distintos precios históricos de compra y venta
        self.assertContains(response, "7600.00")
        self.assertContains(response, "7650.00")
        self.assertContains(response, "7750.00")
        self.assertContains(response, "7800.00")
        self.assertContains(response, "7880.00")
        self.assertContains(response, "7930.00")
        self.assertContains(response, "7950.00")
        self.assertContains(response, "8000.00")

    def test_criterio_3_descarga_reporte_historial_csv(self):
        """
        Criterio 3: Debe existir la opción de descargar el reporte de ese historial (CSV).
        """
        self.client.force_login(self.usuario)
        response = self.client.get(reverse('descargar_reporte_historial'), {
            'moneda_origen': 'USD',
            'moneda_destino': 'PYG',
        })

        self.assertEqual(response.status_code, 200)
        # Verificar cabeceras HTTP de archivo adjunto CSV
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('.csv', response['Content-Disposition'])

        # Verificar contenido estructurado del CSV
        content = response.content.decode('utf-8-sig')
        self.assertIn('Moneda Origen', content)
        self.assertIn('Moneda Destino', content)
        self.assertIn('Precio Compra', content)
        self.assertIn('Precio Venta', content)
        self.assertIn('7950.00', content)
        self.assertIn('7880.00', content)
        self.assertIn('7750.00', content)
        self.assertIn('7600.00', content)


