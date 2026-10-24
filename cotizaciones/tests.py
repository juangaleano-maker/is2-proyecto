from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from decimal import Decimal
import time
from django.utils import timezone

from monedas.models import Moneda
from cotizaciones.models import Cotizacion, Operacion, AlertaTasa, NotificacionTasa
from cotizaciones.forms import AlertaTasaForm
from clientes.models import Cliente


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


class VisitanteTestCase(TestCase):
    """
    Pruebas unitarias para la Historia de Usuario IS2-20:
    'Consultar tasas de cambio como visitante (sin login)'.
    """

    def setUp(self):
        self.client = Client()
        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)
        self.cotizacion = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7800.00'),
            venta=Decimal('7900.00'),
            activo=True,
        )

    def test_visitante_accede_sin_login(self):
        """Un visitante anónimo puede acceder a la vista pública de tasas sin autenticarse."""
        response = self.client.get(reverse('tasas_visitante'))
        self.assertEqual(response.status_code, 200)

    def test_visitante_ve_tasas_compra_y_venta(self):
        """El visitante puede ver las tasas de compra y venta de cada moneda disponible."""
        response = self.client.get(reverse('tasas_visitante'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'7800.00', response.content)
        self.assertIn(b'7900.00', response.content)
        self.assertIn(b'USD', response.content)
        self.assertIn(b'PYG', response.content)

    def test_visitante_ve_simulador_de_conversion(self):
        """La página de visitante incluye el simulador de conversión."""
        response = self.client.get(reverse('tasas_visitante'))
        self.assertContains(response, 'Simulador')

    def test_visitante_puede_filtrar_por_moneda(self):
        """El visitante puede usar los filtros de moneda para acotar los resultados."""
        response = self.client.get(reverse('tasas_visitante') + '?moneda_origen=USD')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'USD', response.content)

from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from monedas.models import Moneda
from .models import Cotizacion
from .services import simular_conversion, obtener_monedas_disponibles, redondear_monto

User = get_user_model()


class SimuladorConversionServiceTest(TestCase):
    """Pruebas unitarias para el servicio de simulación de conversión (IS2-10)."""

    def setUp(self):
        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)
        self.brl = Moneda.objects.create(nombre='Real Brasileño', siglas='BRL', activa=True)

        # Cotización activa USD -> PYG
        self.cot_usd_pyg = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7500.00'),
            venta=Decimal('7600.00'),
            activo=True
        )
        # Cotización activa BRL -> PYG
        self.cot_brl_pyg = Cotizacion.objects.create(
            moneda_origen=self.brl,
            moneda_destino=self.pyg,
            compra=Decimal('1350.00'),
            venta=Decimal('1400.00'),
            activo=True
        )

    def test_obtener_monedas_disponibles(self):
        monedas = obtener_monedas_disponibles()
        codigos = [m[0] for m in monedas]
        self.assertIn('USD', codigos)
        self.assertIn('PYG', codigos)

    def test_simulacion_misma_moneda(self):
        """Conversión entre la misma moneda debe tener tasa 1:1."""
        res = simular_conversion('USD', 'USD', '100.00')
        self.assertTrue(res['exito'])
        self.assertEqual(res['monto_origen'], Decimal('100.00'))
        self.assertEqual(res['monto_destino'], Decimal('100.00'))
        self.assertEqual(res['tasa_aplicada'], Decimal('1.0'))
        self.assertEqual(res['tipo_operacion'], 'paridad')
        self.assertIsNone(res['fecha_tasa'])

    def test_simulacion_par_directo_vigente(self):
        """Conversión directa USD -> PYG debe usar precio de compra vigente."""
        res = simular_conversion('USD', 'PYG', '100.00')
        self.assertTrue(res['exito'])
        self.assertEqual(res['monto_origen'], Decimal('100.00'))
        # 100 * 7500 = 750.000 PYG
        self.assertEqual(res['monto_destino'], Decimal('750000'))
        self.assertEqual(res['tasa_aplicada'], Decimal('7500.00'))
        self.assertEqual(res['cotizacion_id'], self.cot_usd_pyg.id)
        self.assertEqual(res['tipo_operacion'], 'compra_directa')

    def test_simulacion_par_inverso_vigente(self):
        """Conversión inversa PYG -> USD debe usar precio de venta vigente."""
        # Usuario tiene 760.000 PYG y quiere USD -> 760.000 / 7600 = 100 USD
        res = simular_conversion('PYG', 'USD', '760000')
        self.assertTrue(res['exito'])
        self.assertEqual(res['monto_origen'], Decimal('760000'))
        self.assertEqual(res['monto_destino'], Decimal('100.00'))
        self.assertEqual(res['cotizacion_id'], self.cot_usd_pyg.id)
        self.assertEqual(res['tipo_operacion'], 'venta_inversa')

    def test_simulacion_triangulada(self):
        """Conversión BRL -> USD triangulada vía PYG."""
        # 10 BRL -> PYG (10 * 1350 = 13.500 PYG) -> USD (13.500 / 7600 = 1.78 USD)
        res = simular_conversion('BRL', 'USD', '10.00')
        self.assertTrue(res['exito'])
        self.assertEqual(res['monto_origen'], Decimal('10.00'))
        self.assertGreater(res['monto_destino'], Decimal('0'))
        self.assertTrue('triangulada' in res['tipo_operacion'])

    def test_simulacion_usa_cotizacion_mas_reciente(self):
        """Si hay varias cotizaciones activas, debe utilizar la más reciente."""
        cot_nueva = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7800.00'),
            venta=Decimal('7900.00'),
            activo=True
        )
        res = simular_conversion('USD', 'PYG', '10')
        self.assertEqual(res['tasa_aplicada'], Decimal('7800.00'))
        self.assertEqual(res['monto_destino'], Decimal('78000'))
        self.assertEqual(res['cotizacion_id'], cot_nueva.id)

    def test_simulacion_ignora_cotizacion_inactiva(self):
        """Las cotizaciones con activo=False no deben utilizarse."""
        self.cot_usd_pyg.activo = False
        self.cot_usd_pyg.save()

        with self.assertRaises(ValueError) as ctx:
            simular_conversion('USD', 'PYG', '100')
        self.assertIn('No se encontró una cotización activa', str(ctx.exception))

    def test_validaciones_monto(self):
        """Debe validar monto nulo, no numérico, negativo o cero."""
        with self.assertRaises(ValueError):
            simular_conversion('USD', 'PYG', '')

        with self.assertRaises(ValueError):
            simular_conversion('USD', 'PYG', 'abc')

        with self.assertRaises(ValueError):
            simular_conversion('USD', 'PYG', '-50')

        with self.assertRaises(ValueError):
            simular_conversion('USD', 'PYG', '0')

    def test_validaciones_monedas(self):
        """Debe validar códigos de moneda no registrados."""
        with self.assertRaises(ValueError) as ctx:
            simular_conversion('XYZ', 'USD', '100')
        self.assertIn('XYZ', str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            simular_conversion('USD', 'XYZ', '100')
        self.assertIn('XYZ', str(ctx.exception))

    def test_simulacion_no_crea_registros_ni_movimientos(self):
        """Criterio de Aceptación 3: La simulación NO genera ningún movimiento real ni afecta la base de datos."""
        total_cotizaciones_antes = Cotizacion.objects.count()
        
        # Ejecutamos múltiples simulaciones
        simular_conversion('USD', 'PYG', '500')
        simular_conversion('PYG', 'USD', '1000000')
        simular_conversion('USD', 'USD', '100')

        total_cotizaciones_despues = Cotizacion.objects.count()
        self.assertEqual(total_cotizaciones_antes, total_cotizaciones_despues)


class SimuladorConversionViewsTest(TestCase):
    """Pruebas para las vistas web y endpoints API de simulación (IS2-10)."""

    def setUp(self):
        self.client = Client()
        self.usuario = User.objects.create_user(
            username='usuario_registrado',
            email='registrado@example.com',
            password='password123'
        )
        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)
        self.cot_usd = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7500.00'),
            venta=Decimal('7600.00'),
            activo=True
        )

    def test_acceso_anonimo_redirige_a_login(self):
        """Un usuario no registrado / no autenticado debe ser redirigido."""
        url_web = reverse('simulador_conversion')
        resp_web = self.client.get(url_web)
        self.assertEqual(resp_web.status_code, 302)

        url_api = reverse('api_simular_conversion')
        resp_api = self.client.get(url_api)
        self.assertEqual(resp_api.status_code, 302)

    def test_usuario_registrado_puede_acceder_vista_web(self):
        """Un usuario registrado autenticado puede abrir la vista del simulador."""
        self.client.force_login(self.usuario)
        url = reverse('simulador_conversion')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Simulador de Conversión")
        self.assertContains(resp, "Garantía de Simulación")

    def test_vista_web_post_simulacion(self):
        """Simulación exitosa vía POST tradicional en vista web."""
        self.client.force_login(self.usuario)
        url = reverse('simulador_conversion')
        resp = self.client.post(url, {
            'moneda_origen': 'USD',
            'moneda_destino': 'PYG',
            'monto': '100',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "750000")

    def test_api_simular_conversion_get(self):
        """Endpoint API con parámetros GET."""
        self.client.force_login(self.usuario)
        url = reverse('api_simular_conversion')
        resp = self.client.get(url, {
            'moneda_origen': 'USD',
            'moneda_destino': 'PYG',
            'monto': '20',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['monto_origen'], '20')
        self.assertEqual(data['monto_destino'], '150000')
        self.assertEqual(data['tasa_aplicada'], '7500.00')

    def test_api_simular_conversion_post_json(self):
        """Endpoint API con JSON POST."""
        self.client.force_login(self.usuario)
        url = reverse('api_simular_conversion')
        resp = self.client.post(
            url,
            data={'moneda_origen': 'USD', 'moneda_destino': 'PYG', 'monto': '10'},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['monto_destino'], '75000')

    def test_api_simular_conversion_parametros_faltantes(self):
        """Endpoint API valida parámetros obligatorios y responde 400."""
        self.client.force_login(self.usuario)
        url = reverse('api_simular_conversion')
        resp = self.client.get(url, {'monto': '50'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['exito'])
        self.assertIn('error', data)

    def test_api_simular_conversion_monto_invalido(self):
        """Endpoint API valida monto negativo y responde 400."""
        self.client.force_login(self.usuario)
        url = reverse('api_simular_conversion')
        resp = self.client.get(url, {
            'moneda_origen': 'USD',
            'moneda_destino': 'PYG',
            'monto': '-100',
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['exito'])


class VentaMonedaTestCase(TestCase):
    """
    Pruebas unitarias e integrales para la Historia de Usuario IS2-16:
    'Venta de Moneda' a nombre de un cliente asignado.
    """

    def setUp(self):
        # 1. Crear usuarios (operador y cliente regular)
        self.user_operador = User.objects.create_user(
            username='operador_carlos',
            email='carlos@exchange.com',
            password='password123'
        )
        grupo_op, _ = Group.objects.get_or_create(name='operador')
        self.user_operador.groups.add(grupo_op)

        self.user_cliente = User.objects.create_user(
            username='cliente_miguel',
            email='miguel@gmail.com',
            password='password123'
        )
        grupo_cl, _ = Group.objects.get_or_create(name='cliente')
        self.user_cliente.groups.add(grupo_cl)

        # 2. Crear divisas
        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)
        self.eur = Moneda.objects.create(nombre='Euro', siglas='EUR', activa=True)

        # 3. Crear clientes (Minorista y VIP)
        self.cliente_minorista = Cliente.objects.create(
            tipo_persona=Cliente.TipoPersona.FISICA,
            segmento=Cliente.Segmento.MINORISTA,
            documento='1234567',
            nombre='Juan',
            apellido='Pérez',
            email='miguel@gmail.com',
            activo=True
        )

        self.cliente_vip = Cliente.objects.create(
            tipo_persona=Cliente.TipoPersona.JURIDICA,
            segmento=Cliente.Segmento.VIP,
            documento='80012345-6',
            razon_social='Inversiones Globales S.A.',
            email='vip@inversiones.com',
            activo=True
        )

        # 4. Crear cotización activa vigente (USD -> PYG: Compra 7900, Venta 7980)
        self.cot_usd_pyg = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7900.00'),
            venta=Decimal('7980.00'),
            activo=True,
            registrado_por=self.user_operador
        )

    def test_autenticacion_requerida_acceso_anonimo(self):
        """
        Criterio 1: La funcionalidad/pantalla debe requerir autenticación válida.
        Un usuario anónimo debe ser redirigido a login.
        """
        url = reverse('operacion_venta')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_usuario_autenticado_puede_acceder(self):
        """Un usuario con sesión activa puede acceder a la pantalla de venta."""
        self.client.force_login(self.user_operador)
        url = reverse('operacion_venta')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cotizaciones/operaciones/venta.html')
        self.assertIn('form', response.context)

    def test_formulario_contiene_campos_requeridos(self):
        """
        Criterio 2: El formulario debe solicitar:
        - Cliente asignado
        - Moneda (divisa)
        - Monto a vender
        - Tasa aplicada
        """
        from cotizaciones.forms import VentaMonedaForm
        form = VentaMonedaForm(user=self.user_operador)
        self.assertIn('cliente', form.fields)
        self.assertIn('moneda', form.fields)
        self.assertIn('monto', form.fields)
        self.assertIn('tasa_aplicada', form.fields)
        self.assertIn('comision', form.fields)

    def test_calculo_automatico_comision_minorista(self):
        """
        Cálculo automático: La comisión correspondiente a cliente minorista (1.5%)
        se computa automáticamente sobre el subtotal antes de confirmar.
        """
        from cotizaciones.services import calcular_comision_operacion
        # 100 USD @ 7900 PYG = 790,000 Subtotal
        # Comisión 1.5% de 790,000 = 11,850 PYG
        # Total neto = 778,150 PYG
        calc = calcular_comision_operacion(
            cliente=self.cliente_minorista,
            monto='100.00',
            tasa_aplicada='7900.00',
            tipo='VENTA'
        )
        self.assertTrue(calc['exito'])
        self.assertEqual(calc['subtotal'], Decimal('790000.00'))
        self.assertEqual(calc['porcentaje_comision'], Decimal('1.5'))
        self.assertEqual(calc['comision'], Decimal('11850.00'))
        self.assertEqual(calc['total_neto'], Decimal('778150.00'))

    def test_calculo_automatico_comision_vip(self):
        """Cálculo automático para cliente VIP aplica 0.5% de comisión."""
        from cotizaciones.services import calcular_comision_operacion
        # 1,000 USD @ 8000 PYG = 8,000,000 Subtotal
        # Comisión 0.5% de 8,000,000 = 40,000 PYG
        # Total neto = 7,960,000 PYG
        calc = calcular_comision_operacion(
            cliente=self.cliente_vip,
            monto='1000.00',
            tasa_aplicada='8000.00',
            tipo='VENTA'
        )
        self.assertTrue(calc['exito'])
        self.assertEqual(calc['porcentaje_comision'], Decimal('0.5'))
        self.assertEqual(calc['comision'], Decimal('40000.00'))
        self.assertEqual(calc['total_neto'], Decimal('7960000.00'))

    def test_registro_operacion_venta_estado_inicial_pendiente(self):
        """
        Criterio 3: Al confirmar la venta:
        - Tipo de transacción: Venta.
        - Estado inicial obligatorio: 'Pendiente'.
        - La operación debe guardarse en la BD.
        """
        self.client.force_login(self.user_operador)
        url = reverse('operacion_venta')
        datos = {
            'cliente': self.cliente_minorista.id,
            'moneda': self.usd.id,
            'monto': '200.00',
            'tasa_aplicada': '7900.00',
        }
        response = self.client.post(url, data=datos)
        
        # Debe redirigir al detalle de la operación creada
        self.assertEqual(response.status_code, 302)
        
        # Verificar la operación en la BD
        operacion = Operacion.objects.filter(cliente=self.cliente_minorista).first()
        self.assertIsNotNone(operacion)
        self.assertEqual(operacion.tipo, Operacion.TipoOperacion.VENTA)
        self.assertEqual(operacion.estado, Operacion.EstadoOperacion.PENDIENTE)
        self.assertEqual(operacion.monto, Decimal('200.00'))
        self.assertEqual(operacion.tasa_aplicada, Decimal('7900.00'))
        # Subtotal: 200 * 7900 = 1,580,000. Comisión 1.5% = 23,700
        self.assertEqual(operacion.comision, Decimal('23700.00'))
        self.assertEqual(operacion.subtotal, Decimal('1580000.00'))
        self.assertEqual(operacion.total_neto, Decimal('1556300.00'))
        self.assertEqual(operacion.registrado_por, self.user_operador)

    def test_validacion_monto_o_tasa_negativa(self):
        """El formulario rechaza montos o tasas menores o iguales a cero."""
        self.client.force_login(self.user_operador)
        url = reverse('operacion_venta')
        
        # Monto negativo
        resp = self.client.post(url, {
            'cliente': self.cliente_minorista.id,
            'moneda': self.usd.id,
            'monto': '-50.00',
            'tasa_aplicada': '7900.00',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Operacion.objects.exists())

        # Tasa cero
        resp = self.client.post(url, {
            'cliente': self.cliente_minorista.id,
            'moneda': self.usd.id,
            'monto': '100.00',
            'tasa_aplicada': '0.00',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Operacion.objects.exists())

    def test_compatibilidad_generica_compra(self):
        """
        La estructura de datos y servicios es genérica y compatible
        para la función simétrica de Compra de Moneda.
        """
        from cotizaciones.services import registrar_operacion_cambio
        operacion, calculo = registrar_operacion_cambio(
            cliente=self.cliente_vip,
            moneda=self.eur,
            tipo=Operacion.TipoOperacion.COMPRA,
            monto='500.00',
            tasa_aplicada='8500.00',
            usuario=self.user_operador
        )
        self.assertEqual(operacion.tipo, Operacion.TipoOperacion.COMPRA)
        self.assertEqual(operacion.estado, Operacion.EstadoOperacion.PENDIENTE)
        # Subtotal: 500 * 8500 = 4,250,000. Comisión VIP 0.5% = 21,250.
        # En compra: Total neto a abonar = subtotal + comision = 4,271,250
        self.assertEqual(operacion.subtotal, Decimal('4250000.00'))
        self.assertEqual(operacion.comision, Decimal('21250.00'))
        self.assertEqual(operacion.total_neto, Decimal('4271250.00'))

    def test_api_calcular_operacion(self):
        """Endpoint JSON de cálculo automático de comisión en tiempo real."""
        self.client.force_login(self.user_operador)
        url = reverse('api_calcular_operacion')
        resp = self.client.get(url, {
            'cliente_id': self.cliente_minorista.id,
            'monto': '150.00',
            'tasa_aplicada': '7950.00',
            'tipo': 'VENTA'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['monto'], 150.0)
        self.assertEqual(data['tasa_aplicada'], 7950.0)
        self.assertEqual(data['subtotal'], 1192500.0)
        self.assertEqual(data['comision'], 17887.5)
        self.assertEqual(data['total_neto'], 1174612.5)

    def test_api_tasa_vigente_operacion(self):
        """Endpoint JSON que devuelve la tasa de referencia vigente para la divisa."""
        self.client.force_login(self.user_operador)
        url = reverse('api_tasa_vigente_operacion', args=[self.usd.id])
        resp = self.client.get(url, {'tipo': 'VENTA'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['tasa_sugerida'], 7900.0)
        self.assertEqual(data['compra'], 7900.0)
        self.assertEqual(data['venta'], 7980.0)

    def test_detalle_operacion_view(self):
        """Visualización del comprobante de operación en estado Pendiente."""
        from cotizaciones.services import registrar_operacion_cambio
        op, _ = registrar_operacion_cambio(
            cliente=self.cliente_minorista,
            moneda=self.usd,
            tipo=Operacion.TipoOperacion.VENTA,
            monto='100.00',
            tasa_aplicada='7900.00',
            usuario=self.user_operador
        )
        self.client.force_login(self.user_operador)
        url = reverse('operacion_detalle', args=[op.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cotizaciones/operaciones/detalle.html')
        self.assertContains(response, f"Operación #{op.id}")
        self.assertContains(response, "PENDIENTE")

    def test_listar_operaciones_view(self):
        """Listado de operaciones con soporte para filtros."""
        from cotizaciones.services import registrar_operacion_cambio
        registrar_operacion_cambio(
            cliente=self.cliente_minorista,
            moneda=self.usd,
            tipo=Operacion.TipoOperacion.VENTA,
            monto='100.00',
            tasa_aplicada='7900.00',
            usuario=self.user_operador
        )
        self.client.force_login(self.user_operador)
        url = reverse('operaciones_lista')
        response = self.client.get(url, {'tipo': 'VENTA', 'estado': 'PENDIENTE'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cotizaciones/operaciones/lista.html')
        self.assertEqual(len(response.context['operaciones']), 1)

# =======================================================================
# Pruebas Unitarias para Historia de Usuario IS2-52:
# "Cancelación de transacción por cambio de cotización"
# =======================================================================

class CancelacionTransaccionCambioCotizacionTests(TestCase):
    """
    Pruebas para los 3 Criterios de Aceptación de IS2-52:
    1. Durante el proceso de pago/confirmación, el sistema valida si la cotización cambió.
    2. Si la cotización cambió, se notifica al usuario.
    3. El sistema permite al usuario cancelar la transacción sin ningún cargo ni movimiento definitivo.
    """

    def setUp(self):
        from clientes.models import Cliente
        from cotizaciones.models import Operacion

        # Usuario autenticado
        self.usuario = User.objects.create_user(
            username='carlos_usuario',
            email='carlos@empresa.com',
            password='testpassword123'
        )

        # Monedas
        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)

        # Cliente
        self.cliente = Cliente.objects.create(
            tipo_persona=Cliente.TipoPersona.FISICA,
            segmento=Cliente.Segmento.MINORISTA,
            documento='4567890',
            nombre='Carlos',
            apellido='Pérez',
            email='carlos@perez.com'
        )

        # Cotización inicial (vigente al crear la orden)
        self.cotizacion_inicial = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7500.00'),
            venta=Decimal('7550.00'),
            activo=True
        )

        # Operación iniciada en estado PENDIENTE con tasa inicial 7500.00
        self.operacion = Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.usd,
            tipo=Operacion.TipoOperacion.COMPRA,
            monto=Decimal('100.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('2.00'),
            estado=Operacion.EstadoOperacion.PENDIENTE
        )

    def test_criterio_1_sin_cambio_cotizacion(self):
        """Si la cotización no cambió, la validación retorna cambio=False."""
        from cotizaciones.services import verificar_cambio_cotizacion

        resultado = verificar_cambio_cotizacion(self.operacion)
        self.assertFalse(resultado['cambio'])
        self.assertEqual(resultado['tasa_inicial'], Decimal('7500.00'))
        self.assertEqual(resultado['tasa_vigente'], Decimal('7500.00'))
        self.assertEqual(resultado['diferencia'], Decimal('0.00'))

    def test_criterio_1_y_2_detecta_cambio_y_genera_notificacion(self):
        """
        Criterios 1 y 2:
        Si la cotización cambió respecto al inicio de la operación, el sistema lo detecta
        y genera la notificación explicativa al usuario.
        """
        from cotizaciones.services import verificar_cambio_cotizacion

        # Desactivar la anterior y registrar una nueva cotización con aumento
        self.cotizacion_inicial.activo = False
        self.cotizacion_inicial.save()

        Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7650.00'),
            venta=Decimal('7700.00'),
            activo=True
        )

        resultado = verificar_cambio_cotizacion(self.operacion)
        self.assertTrue(resultado['cambio'])
        self.assertEqual(resultado['tasa_inicial'], Decimal('7500.00'))
        self.assertEqual(resultado['tasa_vigente'], Decimal('7650.00'))
        self.assertEqual(resultado['diferencia'], Decimal('150.00'))
        self.assertIsNotNone(resultado['notificacion'])
        self.assertIn("cambió respecto al inicio de la operación", resultado['notificacion'])
        self.assertIn("7500", resultado['notificacion'])
        self.assertIn("7650", resultado['notificacion'])

    def test_criterio_3_cancelar_operacion_sin_cargos_ni_movimientos(self):
        """
        Criterio 3:
        Permite al usuario cancelar la transacción sin que se registre ningún cargo
        ni movimiento financiero definitivo (comisión=0, estado=CANCELADA).
        """
        from cotizaciones.models import Operacion
        from cotizaciones.services import cancelar_operacion_por_cambio_tasa

        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.PENDIENTE)
        self.assertGreater(self.operacion.comision, Decimal('0.00'))

        op_cancelada = cancelar_operacion_por_cambio_tasa(self.operacion, motivo="Cambio de cotización")

        self.assertEqual(op_cancelada.estado, Operacion.EstadoOperacion.CANCELADA)
        # Verificación explícita de no cargos ni comisión
        self.assertEqual(op_cancelada.comision, Decimal('0.00'))

        # Recargar de BD para asegurar persistencia
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.EstadoOperacion.CANCELADA)
        self.assertEqual(self.operacion.comision, Decimal('0.00'))

    def test_no_se_puede_cancelar_operacion_ya_pagada(self):
        """Una operación pagada y completada no puede ser cancelada retroactivamente."""
        from cotizaciones.models import Operacion
        from cotizaciones.services import cancelar_operacion_por_cambio_tasa

        self.operacion.estado = Operacion.EstadoOperacion.PAGADA
        self.operacion.save()

        with self.assertRaises(ValueError):
            cancelar_operacion_por_cambio_tasa(self.operacion)

    def test_confirmar_pago_requiere_aceptar_cambio_de_tasa(self):
        """Si la tasa cambió, no se puede pagar sin aceptar expresamente la nueva cotización."""
        from cotizaciones.services import confirmar_y_pagar_operacion

        # Modificar cotización
        self.cotizacion_inicial.activo = False
        self.cotizacion_inicial.save()
        Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7800.00'),
            venta=Decimal('7850.00'),
            activo=True
        )

        # Intento de pagar sin aceptar nueva tasa -> debe fallar
        with self.assertRaises(ValueError):
            confirmar_y_pagar_operacion(self.operacion, aceptar_cambio_tasa=False)

        # Si el usuario acepta la nueva tasa -> debe proceder y actualizar la tasa aplicada
        op_pagada = confirmar_y_pagar_operacion(self.operacion, aceptar_cambio_tasa=True)
        self.assertEqual(op_pagada.tasa_aplicada, Decimal('7800.00'))
        self.assertEqual(op_pagada.estado, op_pagada.EstadoOperacion.PAGADA)

    def test_vista_confirmar_operacion_pago_muestra_alerta(self):
        """La vista web de confirmación muestra la advertencia cuando la tasa cambia."""
        self.client.force_login(self.usuario)

        # Cambiar cotización
        self.cotizacion_inicial.activo = False
        self.cotizacion_inicial.save()
        Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7700.00'),
            venta=Decimal('7750.00'),
            activo=True
        )

        url = reverse('confirmar_operacion_pago', kwargs={'operacion_id': self.operacion.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "La cotización de la moneda ha cambiado")
        self.assertContains(resp, "Cancelar Transacción (Sin Cargos)")
        self.assertContains(resp, "Aceptar Nueva Cotización y Pagar")

    def test_vista_cancelar_operacion(self):
        """Al enviar la solicitud de cancelación desde la vista web, la operación pasa a CANCELADA sin cargos."""
        self.client.force_login(self.usuario)
        url = reverse('cancelar_operacion', kwargs={'operacion_id': self.operacion.id})

        resp = self.client.post(url, {'motivo': 'No estoy de acuerdo con el nuevo precio'})

        self.assertRedirects(resp, reverse('listar_operaciones'))
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, self.operacion.EstadoOperacion.CANCELADA)
        self.assertEqual(self.operacion.comision, Decimal('0.00'))

    def test_api_validar_tasa_y_api_cancelar(self):
        """Endpoints API JSON para validar tasa y cancelar sin cargos."""
        self.client.force_login(self.usuario)

        # API Validar tasa
        url_validar = reverse('api_validar_tasa_operacion', kwargs={'operacion_id': self.operacion.id})
        resp_val = self.client.get(url_validar)
        self.assertEqual(resp_val.status_code, 200)
        data_val = resp_val.json()
        self.assertTrue(data_val['exito'])
        self.assertEqual(data_val['tasa_inicial'], 7500.0)

        # API Cancelar operación
        url_cancelar = reverse('api_cancelar_operacion', kwargs={'operacion_id': self.operacion.id})
        resp_canc = self.client.post(url_cancelar, content_type='application/json')
        self.assertEqual(resp_canc.status_code, 200)
        data_canc = resp_canc.json()
        self.assertTrue(data_canc['exito'])
        self.assertEqual(data_canc['estado'], 'CANCELADA')
        self.assertEqual(data_canc['comision'], 0.0)


class AlertasYNotificacionesTasasTestCase(TestCase):
    """
    Pruebas para las historias de usuario IS2-57 (Configuración de alertas de tasas)
    e IS2-58 (Envío de notificaciones por variación de tasa).
    """

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='cliente_notif',
            email='notif@test.com',
            password='password123'
        )
        self.usd = Moneda.objects.create(nombre='Dólar Estadounidense', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní Paraguayo', siglas='PYG', activa=True)
        self.eur = Moneda.objects.create(nombre='Euro', siglas='EUR', activa=True)

    def test_creacion_alerta_variacion_y_umbral(self):
        """Verifica la persistencia de AlertaTasa asociada al usuario (IS2-57 Criterio 2)."""
        alerta_var = AlertaTasa.objects.create(
            usuario=self.usuario,
            moneda=self.usd,
            tipo=AlertaTasa.TipoAlerta.VARIACION,
            activa=True
        )
        self.assertTrue(alerta_var.activa)
        self.assertIn("USD", str(alerta_var))

        alerta_umbral = AlertaTasa.objects.create(
            usuario=self.usuario,
            moneda=self.usd,
            tipo=AlertaTasa.TipoAlerta.COMPRA_MAYOR,
            valor_objetivo=Decimal('7800.00'),
            activa=True
        )
        self.assertEqual(alerta_umbral.valor_objetivo, Decimal('7800.00'))

    def test_alerta_tasa_form_validacion(self):
        """El formulario valida que se requiera valor objetivo si no es tipo VARIACION."""
        # Inválido: COMPRA_MAYOR sin valor objetivo
        form_invalido = AlertaTasaForm(data={
            'moneda': self.usd.id,
            'tipo': AlertaTasa.TipoAlerta.COMPRA_MAYOR,
            'valor_objetivo': ''
        })
        self.assertFalse(form_invalido.is_valid())

        # Válido: VARIACION sin valor objetivo
        form_valido_var = AlertaTasaForm(data={
            'moneda': self.usd.id,
            'tipo': AlertaTasa.TipoAlerta.VARIACION,
            'valor_objetivo': ''
        })
        self.assertTrue(form_valido_var.is_valid())

        # Válido: COMPRA_MAYOR con valor objetivo
        form_valido_umbral = AlertaTasaForm(data={
            'moneda': self.usd.id,
            'tipo': AlertaTasa.TipoAlerta.COMPRA_MAYOR,
            'valor_objetivo': '7800.00'
        })
        self.assertTrue(form_valido_umbral.is_valid())

    def test_signal_notificacion_por_variacion_tasa(self):
        """Al crear/actualizar cotización, se verifica alerta y se notifica al usuario (IS2-58)."""
        # Usuario sigue variaciones de USD
        AlertaTasa.objects.create(
            usuario=self.usuario,
            moneda=self.usd,
            tipo=AlertaTasa.TipoAlerta.VARIACION,
            activa=True
        )

        # Se registra una nueva cotización de USD
        cot = Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7800.00'),
            venta=Decimal('7850.00'),
            activo=True
        )

        notificaciones = NotificacionTasa.objects.filter(usuario=self.usuario)
        self.assertEqual(notificaciones.count(), 1)
        notif = notificaciones.first()
        self.assertEqual(notif.moneda, self.usd)
        self.assertEqual(notif.tasa_compra, Decimal('7800.00'))
        self.assertEqual(notif.tasa_venta, Decimal('7850.00'))
        self.assertIn("USD", notif.mensaje)
        self.assertFalse(notif.leida)

    def test_signal_evaluacion_umbral_compra(self):
        """La notificación se dispara solo si cumple la condición del umbral configurado (IS2-58 Criterio 1)."""
        # Alerta: compra >= 7900
        AlertaTasa.objects.create(
            usuario=self.usuario,
            moneda=self.usd,
            tipo=AlertaTasa.TipoAlerta.COMPRA_MAYOR,
            valor_objetivo=Decimal('7900.00'),
            activa=True
        )

        # 1. Cotización por debajo: compra = 7800 (NO cumple)
        Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7800.00'),
            venta=Decimal('7850.00'),
            activo=True
        )
        self.assertEqual(NotificacionTasa.objects.filter(usuario=self.usuario).count(), 0)

        # 2. Cotización que alcanza la meta: compra = 7920 (CUMPLE)
        Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7920.00'),
            venta=Decimal('7980.00'),
            activo=True
        )
        self.assertEqual(NotificacionTasa.objects.filter(usuario=self.usuario).count(), 1)

    def test_signal_notifica_a_todos_los_clientes_sin_alerta_configurada(self):
        """Los clientes sin alertas personalizadas también reciben la notificación de cotización nueva."""
        cliente_sin_alerta = User.objects.create_user(
            username='cliente_sin_alerta_test',
            email='cliente_sin_alerta@test.com',
            password='password123'
        )
        Cotizacion.objects.create(
            moneda_origen=self.eur,
            moneda_destino=self.pyg,
            compra=Decimal('8200.00'),
            venta=Decimal('8300.00'),
            activo=True
        )
        notifs = NotificacionTasa.objects.filter(usuario=cliente_sin_alerta, moneda=self.eur)
        self.assertEqual(notifs.count(), 1)
        self.assertIn("EUR", notifs.first().titulo)

    def test_api_toggle_moneda_seguimiento(self):
        """Prueba del botón de seguimiento rápido en 1 clic para estar al pendiente."""
        self.client.force_login(self.usuario)
        url = reverse('api_toggle_moneda_seguimiento', kwargs={'moneda_id': self.usd.id})

        # 1. Activar seguimiento
        resp1 = self.client.post(url)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1['exito'])
        self.assertTrue(data1['siguiendo'])
        self.assertTrue(AlertaTasa.objects.filter(usuario=self.usuario, moneda=self.usd, activa=True).exists())

        # 2. Desactivar seguimiento con segundo clic
        resp2 = self.client.post(url)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2['exito'])
        self.assertFalse(data2['siguiendo'])
        self.assertFalse(AlertaTasa.objects.filter(usuario=self.usuario, moneda=self.usd).exists())

    def test_api_notificaciones_y_marcar_leidas(self):
        """Prueba de los endpoints consumidos por la campanita del navbar."""
        self.client.force_login(self.usuario)

        # Crear notificación de prueba
        NotificacionTasa.objects.create(
            usuario=self.usuario,
            moneda=self.usd,
            titulo="Variación USD",
            mensaje="Tasa actualizada",
            tasa_compra=Decimal('7800.00'),
            tasa_venta=Decimal('7850.00'),
            fecha_actualizacion=timezone.now(),
            leida=False
        )

        # GET API Notificaciones
        url_notifs = reverse('api_notificaciones')
        resp = self.client.get(url_notifs)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['no_leidas_count'], 1)
        self.assertEqual(len(data['notificaciones']), 1)
        self.assertEqual(data['notificaciones'][0]['moneda'], 'USD')

        # POST Marcar leídas
        url_marcar = reverse('api_marcar_notificaciones_leidas')
        resp_post = self.client.post(url_marcar)
        self.assertEqual(resp_post.status_code, 200)
        data_post = resp_post.json()
        self.assertTrue(data_post['exito'])
        self.assertEqual(data_post['actualizadas'], 1)

        # Verificar que el contador quedó en 0
        resp_after = self.client.get(url_notifs)
        self.assertEqual(resp_after.json()['no_leidas_count'], 0)

    def test_vista_configurar_alertas_get_y_post(self):
        """Prueba de la vista completa de alertas /cotizaciones/alertas/."""
        self.client.force_login(self.usuario)
        url = reverse('alertas_tasas')

        # GET
        resp_get = self.client.get(url)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, "Alertas y Notificaciones de Tasas")

        # POST Crear alerta
        resp_post = self.client.post(url, {
            'moneda': self.usd.id,
            'tipo': AlertaTasa.TipoAlerta.VENTA_MENOR,
            'valor_objetivo': '7700.00'
        })
        self.assertRedirects(resp_post, url)
        self.assertTrue(AlertaTasa.objects.filter(
            usuario=self.usuario,
            tipo=AlertaTasa.TipoAlerta.VENTA_MENOR,
            valor_objetivo=Decimal('7700.00')
        ).exists())

    def test_eliminar_alerta(self):
        """El usuario puede eliminar una alerta que haya configurado."""
        alerta = AlertaTasa.objects.create(
            usuario=self.usuario,
            moneda=self.usd,
            tipo=AlertaTasa.TipoAlerta.VARIACION
        )
        self.client.force_login(self.usuario)
        url = reverse('eliminar_alerta', kwargs={'alerta_id': alerta.id})

        resp = self.client.post(url)
        self.assertRedirects(resp, reverse('alertas_tasas'))
        self.assertFalse(AlertaTasa.objects.filter(id=alerta.id).exists())


# ===========================================================================
# Tests de Apertura y Cierre de Caja (IS2-60)
# ===========================================================================

class SesionCajaModelTestCase(TestCase):
    """
    Pruebas unitarias para el modelo SesionCaja (IS2-60).
    Cubre la creación de apertura, la prevención de duplicados,
    el cálculo correcto de saldo esperado y la detección de
    diferencias (faltante, sobrante, exacto).
    """

    def setUp(self):
        from cotizaciones.models import SesionCaja

        # Grupos necesarios
        self.grupo_cajero = Group.objects.get_or_create(name='cajero')[0]

        # Cajero de prueba
        self.cajero = User.objects.create_user(
            username='cajero_test',
            password='secret123',
            first_name='Juan',
            last_name='Cajero',
        )
        self.cajero.groups.add(self.grupo_cajero)

        # Monedas y cliente para operaciones
        self.usd = Moneda.objects.create(nombre='Dólar', siglas='USD', activa=True)
        self.pyg = Moneda.objects.create(nombre='Guaraní', siglas='PYG', activa=True)
        self.cliente = Cliente.objects.create(
            nombre='Cliente',
            apellido='Caja',
            documento='999999',
            tipo_persona='FISICA',
            email='cajero@test.com',
            activo=True,
        )

        # Cotización vigente
        Cotizacion.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal('7500.00'),
            venta=Decimal('7600.00'),
            activo=True,
            registrado_por=self.cajero,
        )

        self.SesionCaja = SesionCaja

    # ------------------------------------------------------------------
    # CA-1: Apertura válida
    # ------------------------------------------------------------------

    def test_crear_sesion_caja_apertura_valida(self):
        """Se puede crear una sesión de caja con monto inicial positivo."""
        sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja 1',
            monto_inicial=Decimal('500000.00'),
        )
        self.assertEqual(sesion.estado, self.SesionCaja.EstadoSesion.ABIERTA)
        self.assertEqual(sesion.monto_inicial, Decimal('500000.00'))
        self.assertEqual(sesion.nombre_caja, 'Caja 1')
        self.assertIsNone(sesion.fecha_cierre)
        self.assertIsNone(sesion.monto_final_declarado)

    # ------------------------------------------------------------------
    # CA-2: No se permite abrir dos sesiones simultáneas para el mismo cajero
    # ------------------------------------------------------------------

    def test_no_se_puede_tener_dos_sesiones_abiertas_mismo_cajero(self):
        """
        El sistema NO debe permitir abrir una segunda sesión mientras
        la primera esté ABIERTA. La vista valida esto; aquí testeamos
        la lógica de consulta directamente (como lo hace la vista).
        """
        # Primera apertura
        self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja Principal',
            monto_inicial=Decimal('300000.00'),
        )

        # Simular la validación que realiza la vista
        sesion_activa_existente = self.SesionCaja.objects.filter(
            cajero=self.cajero,
            estado=self.SesionCaja.EstadoSesion.ABIERTA,
        ).first()

        self.assertIsNotNone(
            sesion_activa_existente,
            'Debe detectarse la sesión abierta existente antes de permitir una nueva apertura.',
        )
        # Confirma que solo hay una sesión abierta
        total_abiertas = self.SesionCaja.objects.filter(
            cajero=self.cajero,
            estado=self.SesionCaja.EstadoSesion.ABIERTA,
        ).count()
        self.assertEqual(total_abiertas, 1)

    # ------------------------------------------------------------------
    # CA-3: Cierre de caja — saldo EXACTO
    # ------------------------------------------------------------------

    def test_cierre_caja_saldo_exacto(self):
        """
        Al cerrar con el monto declarado igual al saldo esperado,
        la diferencia debe ser exactamente cero y el tipo 'EXACTO'.
        """
        sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja Principal',
            monto_inicial=Decimal('1000000.00'),
        )
        # Sin operaciones → saldo esperado == monto inicial
        saldo_esperado = sesion.calcular_saldo_esperado()
        self.assertEqual(saldo_esperado, Decimal('1000000.00'))

        sesion.cerrar(monto_final_declarado=Decimal('1000000.00'))

        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, self.SesionCaja.EstadoSesion.CERRADA)
        self.assertEqual(sesion.saldo_esperado, Decimal('1000000.00'))
        self.assertEqual(sesion.monto_final_declarado, Decimal('1000000.00'))
        self.assertEqual(sesion.diferencia, Decimal('0.00'))
        self.assertEqual(sesion.tipo_diferencia, 'EXACTO')
        self.assertIsNotNone(sesion.fecha_cierre)

    # ------------------------------------------------------------------
    # CA-4: Cierre de caja — FALTANTE
    # ------------------------------------------------------------------

    def test_cierre_caja_faltante(self):
        """
        Si el monto declarado es MENOR al saldo esperado,
        la diferencia es negativa y el tipo debe ser 'FALTANTE'.
        """
        sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja 2',
            monto_inicial=Decimal('500000.00'),
        )
        # Declarar menos de lo esperado
        sesion.cerrar(monto_final_declarado=Decimal('450000.00'))

        sesion.refresh_from_db()
        self.assertEqual(sesion.diferencia, Decimal('-50000.00'))
        self.assertEqual(sesion.tipo_diferencia, 'FALTANTE')

    # ------------------------------------------------------------------
    # CA-5: Cierre de caja — SOBRANTE
    # ------------------------------------------------------------------

    def test_cierre_caja_sobrante(self):
        """
        Si el monto declarado es MAYOR al saldo esperado,
        la diferencia es positiva y el tipo debe ser 'SOBRANTE'.
        """
        sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja 3',
            monto_inicial=Decimal('200000.00'),
        )
        # Declarar más de lo esperado
        sesion.cerrar(monto_final_declarado=Decimal('220000.00'))

        sesion.refresh_from_db()
        self.assertEqual(sesion.diferencia, Decimal('20000.00'))
        self.assertEqual(sesion.tipo_diferencia, 'SOBRANTE')

    # ------------------------------------------------------------------
    # CA-6: El saldo esperado incorpora operaciones pagadas del turno
    # ------------------------------------------------------------------

    def test_saldo_esperado_incluye_operaciones_del_turno(self):
        """
        El saldo esperado debe calcularse correctamente sumando ingresos
        y restando egresos de las operaciones PAGADAS del turno.
        """
        sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja Con Ops',
            monto_inicial=Decimal('1000000.00'),
        )

        # Operación de COMPRA (el cajero recibe moneda local)
        # monto=10 USD, tasa=7500 → subtotal=75000 PYG (ingreso)
        op_compra = Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.usd,
            tipo=Operacion.TipoOperacion.COMPRA,
            monto=Decimal('10.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=Operacion.EstadoOperacion.PAGADA,
            registrado_por=self.cajero,
        )

        # Operación de VENTA (el cajero entrega moneda local)
        # monto=5 USD, tasa=7600 → subtotal=38000 PYG (egreso)
        op_venta = Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.usd,
            tipo=Operacion.TipoOperacion.VENTA,
            monto=Decimal('5.00'),
            tasa_aplicada=Decimal('7600.00'),
            comision=Decimal('0.00'),
            estado=Operacion.EstadoOperacion.PAGADA,
            registrado_por=self.cajero,
        )

        saldo = sesion.calcular_saldo_esperado()
        # 1_000_000 + 75_000 (ingreso compra) - 38_000 (egreso venta) = 1_037_000
        self.assertEqual(saldo, Decimal('1037000.00'))

    # ------------------------------------------------------------------
    # CA-7: Operaciones PENDIENTES o CANCELADAS no afectan el saldo
    # ------------------------------------------------------------------

    def test_operaciones_no_pagadas_no_afectan_saldo(self):
        """Las operaciones PENDIENTES o CANCELADAS NO deben sumarse al saldo esperado."""
        sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja Solo Pendientes',
            monto_inicial=Decimal('500000.00'),
        )

        # Operación PENDIENTE — no debe contarse
        Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.usd,
            tipo=Operacion.TipoOperacion.COMPRA,
            monto=Decimal('100.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=Operacion.EstadoOperacion.PENDIENTE,
            registrado_por=self.cajero,
        )

        saldo = sesion.calcular_saldo_esperado()
        self.assertEqual(saldo, Decimal('500000.00'))


class SesionCajaViewTestCase(TestCase):
    """
    Pruebas de integración para las vistas de Apertura y Cierre de Caja.
    """

    def setUp(self):
        from cotizaciones.models import SesionCaja

        self.grupo_cajero = Group.objects.get_or_create(name='cajero')[0]
        self.cajero = User.objects.create_user(
            username='cajero_view_test',
            password='secret123',
        )
        self.cajero.groups.add(self.grupo_cajero)
        self.client = Client()
        self.SesionCaja = SesionCaja

    def test_vista_apertura_requiere_login(self):
        """Un usuario no autenticado es redirigido al login."""
        resp = self.client.get(reverse('apertura_caja'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_vista_dashboard_requiere_login(self):
        """El dashboard de caja requiere autenticación."""
        resp = self.client.get(reverse('caja_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_vista_cierre_requiere_login(self):
        """El cierre de caja requiere autenticación."""
        resp = self.client.get(reverse('cierre_caja'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_cajero_puede_ver_formulario_apertura(self):
        """Un cajero autenticado puede acceder al formulario de apertura y ver inputs de billetes."""
        from monedas.models import Moneda, DenominacionMoneda
        moneda_usd = Moneda.objects.create(nombre='Dólar Test', siglas='USDT', activa=True)
        d_test = DenominacionMoneda.objects.create(moneda=moneda_usd, valor=Decimal('20.00'), activo=True)
        self.client.force_login(self.cajero)
        resp = self.client.get(reverse('apertura_caja'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Apertura de Caja')
        self.assertContains(resp, f'name="cant_billete_{d_test.id}"')
        self.assertNotContains(resp, 'name="cant_billete_{d.id}"')

    def test_cajero_puede_aperturar_caja_via_post(self):
        """Un POST válido crea una SesionCaja y redirige al dashboard."""
        self.client.force_login(self.cajero)
        resp = self.client.post(reverse('apertura_caja'), {
            'nombre_caja': 'Caja Test',
            'monto_inicial': '750000.00',
        })
        self.assertRedirects(resp, reverse('caja_dashboard'))
        sesiones = self.SesionCaja.objects.filter(cajero=self.cajero, estado='ABIERTA')
        self.assertEqual(sesiones.count(), 1)
        self.assertEqual(sesiones.first().monto_inicial, Decimal('750000.00'))

    def test_cajero_con_sesion_abierta_redirige_al_intentar_nueva_apertura(self):
        """Si ya hay sesión abierta, el GET a apertura redirige al dashboard."""
        self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja Ya Abierta',
            monto_inicial=Decimal('300000.00'),
        )
        self.client.force_login(self.cajero)
        resp = self.client.get(reverse('apertura_caja'))
        self.assertRedirects(resp, reverse('caja_dashboard'))

    def test_vista_cierre_sin_sesion_abierta_redirige_a_apertura(self):
        """Si no hay sesión abierta, el cierre redirige a la apertura."""
        self.client.force_login(self.cajero)
        resp = self.client.get(reverse('cierre_caja'))
        self.assertRedirects(resp, reverse('apertura_caja'))

    def test_cajero_puede_cerrar_caja_via_post(self):
        """Un POST válido de cierre actualiza la sesión a CERRADA con arqueo calculado."""
        sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja Para Cerrar',
            monto_inicial=Decimal('1000000.00'),
        )
        self.client.force_login(self.cajero)
        resp = self.client.post(reverse('cierre_caja'), {
            'monto_final_declarado': '950000.00',
            'observaciones': 'Cierre de prueba',
        })
        self.assertRedirects(resp, reverse('caja_dashboard'))

        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, self.SesionCaja.EstadoSesion.CERRADA)
        self.assertEqual(sesion.monto_final_declarado, Decimal('950000.00'))
        self.assertEqual(sesion.saldo_esperado, Decimal('1000000.00'))
        self.assertEqual(sesion.diferencia, Decimal('-50000.00'))
        self.assertEqual(sesion.tipo_diferencia, 'FALTANTE')


# =======================================================================
# TESTS: Registro de Movimientos de Caja (IS2-61)
# =======================================================================

class MovimientoCajaTestCase(TestCase):
    """
    Tests para IS2-61:
    - Criterio 1: Registro automático de transacciones (compra/venta) en caja activa
    - Criterio 2: Operación compra = INGRESO, operación venta = EGRESO
    - Criterio 3: Actualización del saldo en tiempo real a través de los movimientos
    - Criterio 4: Bloqueo de confirmación de pago si no hay caja abierta
    - Criterio 5: Vista de historial de movimientos accesible
    """

    def setUp(self):
        from .models import SesionCaja, MovimientoCaja, Operacion
        from monedas.models import Moneda
        from clientes.models import Cliente
        self.SesionCaja = SesionCaja
        self.MovimientoCaja = MovimientoCaja
        self.Operacion = Operacion

        self.grupo_cajero = Group.objects.get_or_create(name='cajero')[0]
        self.cajero = User.objects.create_user(
            username='cajero_mov',
            password='Password123!',
            email='cajero_mov@test.com',
            first_name='Cajero',
            last_name='Movimientos',
        )
        self.cajero.groups.add(self.grupo_cajero)


        self.cliente = Cliente.objects.create(
            tipo_persona=Cliente.TipoPersona.FISICA,
            documento='9876543',
            nombre='Cliente',
            apellido='Prueba',
            email='cliente_prueba@test.com',
            telefono='0981123456',
        )

        self.moneda = Moneda.objects.create(
            nombre='Dólar Estadounidense',
            siglas='USD',
            activa=True,
        )

        # Crear sesión abierta con fondo inicial de 1.000.000 Gs.
        self.sesion = self.SesionCaja.objects.create(
            cajero=self.cajero,
            nombre_caja='Caja Principal',
            monto_inicial=Decimal('1000000.00'),
            estado=self.SesionCaja.EstadoSesion.ABIERTA,
        )


    def test_operacion_compra_pagada_crea_movimiento_ingreso(self):
        """
        Una compra pagada (cliente vende dólares a la casa de cambios) genera
        un movimiento de tipo INGRESO en la caja activa con el subtotal correspondiente.
        """
        op = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.COMPRA,
            monto=Decimal('100.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PENDIENTE,
            registrado_por=self.cajero,
        )

        # Confirmar la operación pasando a PAGADA
        op.estado = self.Operacion.EstadoOperacion.PAGADA
        op.save()

        # Debe haberse creado un MovimientoCaja automáticamente
        movs = self.MovimientoCaja.objects.filter(operacion=op)
        self.assertEqual(movs.count(), 1)
        mov = movs.first()
        self.assertEqual(mov.sesion, self.sesion)
        self.assertEqual(mov.tipo, self.MovimientoCaja.TipoMovimiento.INGRESO)
        self.assertEqual(mov.monto, Decimal('750000.00'))  # 100 * 7500
        self.assertEqual(mov.registrado_por, self.cajero)

    def test_operacion_venta_pagada_crea_movimiento_egreso(self):
        """
        Una venta pagada genera un movimiento de tipo EGRESO en la caja activa.
        """
        op = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.VENTA,
            monto=Decimal('50.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PENDIENTE,
            registrado_por=self.cajero,
        )

        op.estado = self.Operacion.EstadoOperacion.PAGADA
        op.save()

        movs = self.MovimientoCaja.objects.filter(operacion=op)
        self.assertEqual(movs.count(), 1)
        mov = movs.first()
        self.assertEqual(mov.sesion, self.sesion)
        self.assertEqual(mov.tipo, self.MovimientoCaja.TipoMovimiento.EGRESO)
        self.assertEqual(mov.monto, Decimal('375000.00'))  # 50 * 7500

    def test_actualizacion_de_saldo_esperado_por_movimientos(self):
        """
        El saldo esperado de la sesión se actualiza sumando ingresos y restando egresos.
        Fondo inicial: 1.000.000 + Ingreso (750.000) - Egreso (375.000) = 1.375.000 Gs.
        """
        # Compra
        op1 = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.COMPRA,
            monto=Decimal('100.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PAGADA,
            registrado_por=self.cajero,
        )

        # Venta
        op2 = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.VENTA,
            monto=Decimal('50.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PAGADA,
            registrado_por=self.cajero,
        )

        ingresos, egresos = self.sesion.calcular_ingresos_turno()
        self.assertEqual(ingresos, Decimal('750000.00'))
        self.assertEqual(egresos, Decimal('375000.00'))
        saldo = self.sesion.calcular_saldo_esperado()
        self.assertEqual(saldo, Decimal('1375000.00'))

    def test_no_crea_movimiento_duplicado_al_guardar_nuevamente(self):
        """Guardar varias veces una operación ya PAGADA no debe duplicar el movimiento."""
        op = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.COMPRA,
            monto=Decimal('100.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PAGADA,
            registrado_por=self.cajero,
        )
        # Volver a llamar save()
        op.save()
        self.assertEqual(self.MovimientoCaja.objects.filter(operacion=op).count(), 1)

    def test_operacion_sin_caja_abierta_no_falla_pero_no_crea_movimiento(self):
        """Si el cajero no tiene caja abierta, la señal registra un log sin lanzar excepción."""
        cajero_sin_caja = User.objects.create_user(username='sin_caja', password='Password123!')
        op = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.COMPRA,
            monto=Decimal('100.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PAGADA,
            registrado_por=cajero_sin_caja,
        )
        self.assertEqual(self.MovimientoCaja.objects.filter(operacion=op).count(), 0)

    def test_bloqueo_confirmacion_pago_si_cajero_no_tiene_caja_abierta(self):
        """
        En la vista confirmar_operacion_pago, si el usuario no tiene caja abierta,
        se le impide confirmar el pago y se le redirige a la apertura de caja.
        """
        # Cerrar la caja activa
        self.sesion.estado = self.SesionCaja.EstadoSesion.CERRADA
        self.sesion.save()

        op = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.COMPRA,
            monto=Decimal('100.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PENDIENTE,
            registrado_por=self.cajero,
        )

        self.client.force_login(self.cajero)
        resp = self.client.post(
            reverse('confirmar_operacion_pago', kwargs={'operacion_id': op.id}),
            {'accion': 'pagar'}
        )
        # Redirige a apertura de caja con mensaje de advertencia
        self.assertRedirects(resp, reverse('apertura_caja'))
        op.refresh_from_db()
        self.assertEqual(op.estado, self.Operacion.EstadoOperacion.PENDIENTE)

    def test_vista_historial_movimientos_accesible(self):
        """La vista historial_movimientos_view responde 200 y renderiza movimientos."""
        self.client.force_login(self.cajero)
        resp = self.client.get(reverse('historial_movimientos'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Historial de Movimientos de Caja')

    def test_apertura_caja_multidivisa_con_conteo_billetes(self):
        """Apertura registra saldo por cada divisa activa y conteo físico de billetes."""
        from monedas.models import DenominacionMoneda
        from .models import SaldoSesionMoneda, ConteoBilleteSesion
        
        # Denominaciones para USD
        d100 = DenominacionMoneda.objects.create(moneda=self.moneda, valor=Decimal('100.00'), activo=True)
        d50 = DenominacionMoneda.objects.create(moneda=self.moneda, valor=Decimal('50.00'), activo=True)

        # Cerrar sesión anterior para permitir abrir una nueva
        self.sesion.estado = self.SesionCaja.EstadoSesion.CERRADA
        self.sesion.save()

        self.client.force_login(self.cajero)
        resp = self.client.post(reverse('apertura_caja'), {
            'nombre_caja': 'Caja Multidivisa Test',
            f'cant_billete_{d100.id}': '10',  # 10 * 100 = 1000 USD
            f'cant_billete_{d50.id}': '4',    # 4 * 50 = 200 USD -> Total 1200 USD
            'monto_inicial': '500000.00',      # 500.000 Gs.
        })
        self.assertRedirects(resp, reverse('caja_dashboard'))

        nueva_sesion = self.SesionCaja.objects.filter(cajero=self.cajero, estado=self.SesionCaja.EstadoSesion.ABIERTA).first()
        self.assertIsNotNone(nueva_sesion)
        self.assertEqual(nueva_sesion.nombre_caja, 'Caja Multidivisa Test')
        
        # SaldoSesionMoneda para USD
        saldo_usd = SaldoSesionMoneda.objects.filter(sesion=nueva_sesion, moneda=self.moneda).first()
        self.assertIsNotNone(saldo_usd)
        self.assertEqual(saldo_usd.monto_inicial, Decimal('1200.00'))

        # Conteo físico de billetes registrado
        conteo = ConteoBilleteSesion.objects.filter(sesion=nueva_sesion, denominacion=d100).first()
        self.assertIsNotNone(conteo)
        self.assertEqual(conteo.cantidad, 10)
        self.assertEqual(conteo.subtotal, Decimal('1000.00'))

    def test_cierre_arqueo_multidivisa_por_billetes_y_diferencias(self):
        """Al cerrar caja se valida el arqueo y diferencias por cada divisa activa."""
        from monedas.models import DenominacionMoneda
        from .models import SaldoSesionMoneda
        
        d100 = DenominacionMoneda.objects.create(moneda=self.moneda, valor=Decimal('100.00'), activo=True)
        saldo_usd = SaldoSesionMoneda.objects.create(
            sesion=self.sesion,
            moneda=self.moneda,
            monto_inicial=Decimal('1000.00'),
        )

        # Operación de venta de 200 USD (entra 200 USD a caja)
        op = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.VENTA,
            monto=Decimal('200.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PAGADA,
            registrado_por=self.cajero,
        )

        # El saldo esperado de USD es 1000 + 200 = 1200 USD
        # El cajero cuenta 11 billetes de 100 = 1100 USD (FALTANTE de 100 USD)
        self.client.force_login(self.cajero)
        resp = self.client.post(reverse('cierre_caja'), {
            f'cant_cierre_billete_{d100.id}': '11',  # 1100 USD
            'monto_final_declarado': '1000000.00',   # Gs.
            'observaciones': 'Faltante de 1 billete de 100 USD',
        })
        self.assertRedirects(resp, reverse('caja_dashboard'))

        saldo_usd.refresh_from_db()
        self.assertEqual(saldo_usd.saldo_esperado, Decimal('1200.00'))
        self.assertEqual(saldo_usd.monto_final_declarado, Decimal('1100.00'))
        self.assertEqual(saldo_usd.diferencia, Decimal('-100.00'))
        self.assertEqual(saldo_usd.tipo_diferencia, 'FALTANTE')

    def test_caja_ignora_monedas_inactivas(self):
        """Monedas con activa=False no aparecen en la apertura ni arqueo de caja."""
        from monedas.models import Moneda
        moneda_inactiva = Moneda.objects.create(nombre="Yen Japonés", siglas="JPY", activa=False)

        # Cerrar sesión activa previa para poder acceder a apertura_caja
        self.sesion.estado = self.SesionCaja.EstadoSesion.CERRADA
        self.sesion.save()

        self.client.force_login(self.cajero)
        resp = self.client.get(reverse('apertura_caja'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "USD")
        self.assertNotContains(resp, "JPY")

    def test_rn16_cajero_sin_caja_abierta_no_puede_acceder_a_compra_ni_venta(self):
        """RN16: Una caja debe encontrarse abierta para que el cajero asociado pueda registrar operaciones sobre ella."""
        self.sesion.estado = self.SesionCaja.EstadoSesion.CERRADA
        self.sesion.save()

        self.client.force_login(self.cajero)
        resp_compra = self.client.get(reverse('comprar_moneda'))
        self.assertRedirects(resp_compra, reverse('apertura_caja'))

        resp_venta = self.client.get(reverse('operacion_venta'))
        self.assertRedirects(resp_venta, reverse('apertura_caja'))

    def test_rn15_operacion_cajero_se_vincula_a_caja_sesion_y_canal_fisico(self):
        """RN15: El cajero registra operaciones sobre su caja asignada en turno activo por canal físico."""
        from .models import Caja
        caja_obj = Caja.objects.create(numero=10, nombre='Caja 10 Test', sucursal='Central')
        self.sesion.caja = caja_obj
        self.sesion.save()

        self.client.force_login(self.cajero)
        resp = self.client.post(reverse('operacion_venta'), {
            'cliente': self.cliente.id,
            'moneda': self.moneda.id,
            'monto': '150.00',
            'tasa_aplicada': '7500.00',
        })
        self.assertEqual(resp.status_code, 302)

        op = self.Operacion.objects.filter(registrado_por=self.cajero).order_by('-id').first()
        self.assertIsNotNone(op)
        self.assertEqual(op.canal, self.Operacion.CanalOperacion.FISICO)
        self.assertEqual(op.caja, caja_obj)
        self.assertEqual(op.sesion_caja, self.sesion)

    def test_rn15_cajero_solo_ve_operaciones_de_su_caja_en_listado(self):
        """RN15 y Jerarquía: El cajero solo accede a operaciones de su caja asignada."""
        from .models import Caja
        caja1 = Caja.objects.create(numero=11, nombre='Caja 11', sucursal='Central')
        caja2 = Caja.objects.create(numero=12, nombre='Caja 12', sucursal='Central')
        self.sesion.caja = caja1
        self.sesion.save()

        # Operación de este cajero en su caja
        op_propia = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.COMPRA,
            monto=Decimal('50.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PENDIENTE,
            registrado_por=self.cajero,
            caja=caja1,
            sesion_caja=self.sesion,
            canal=self.Operacion.CanalOperacion.FISICO,
        )

        # Operación de otro cajero en otra caja
        otro_cajero = User.objects.create_user(username='otro_cajero', password='Password123!')
        otro_cajero.groups.add(self.grupo_cajero)
        op_ajena = self.Operacion.objects.create(
            cliente=self.cliente,
            moneda=self.moneda,
            tipo=self.Operacion.TipoOperacion.VENTA,
            monto=Decimal('80.00'),
            tasa_aplicada=Decimal('7500.00'),
            comision=Decimal('0.00'),
            estado=self.Operacion.EstadoOperacion.PENDIENTE,
            registrado_por=otro_cajero,
            caja=caja2,
            canal=self.Operacion.CanalOperacion.FISICO,
        )

        self.client.force_login(self.cajero)
        resp = self.client.get(reverse('listar_operaciones'))
        self.assertEqual(resp.status_code, 200)
        operaciones_en_contexto = list(resp.context['operaciones'])
        self.assertIn(op_propia, operaciones_en_contexto)
        self.assertNotIn(op_ajena, operaciones_en_contexto)

    def test_arqueo_con_diferencia_de_piezas_y_actualizacion_stock(self):
        """Arqueo: compara billetes de sistema con contados físicamente y actualiza StockBilleteCaja."""
        from monedas.models import DenominacionMoneda
        from .models import Caja, ConteoBilleteSesion, StockBilleteCaja
        caja_obj = Caja.objects.create(numero=13, nombre='Caja 13 Arqueo', sucursal='Central')
        self.sesion.caja = caja_obj
        self.sesion.save()

        d100 = DenominacionMoneda.objects.create(moneda=self.moneda, valor=Decimal('100.00'), activo=True)

        # Apertura: registrar 5 billetes de 100
        ConteoBilleteSesion.objects.create(
            sesion=self.sesion,
            denominacion=d100,
            momento=ConteoBilleteSesion.MomentoConteo.APERTURA,
            cantidad=5,
            cantidad_sistema=5,
            diferencia_piezas=0,
        )
        StockBilleteCaja.objects.create(caja=caja_obj, denominacion=d100, cantidad=5)

        # Cierre: contar 6 billetes (1 de sobra)
        self.client.force_login(self.cajero)
        resp = self.client.post(reverse('cierre_caja'), {
            f'cant_cierre_billete_{d100.id}': '6',
            'monto_final_declarado': '1000000.00',
        })
        self.assertRedirects(resp, reverse('caja_dashboard'))

        conteo_cierre = ConteoBilleteSesion.objects.filter(
            sesion=self.sesion,
            momento=ConteoBilleteSesion.MomentoConteo.CIERRE,
            denominacion=d100
        ).first()
        self.assertIsNotNone(conteo_cierre)
        self.assertEqual(conteo_cierre.cantidad_sistema, 5)
        self.assertEqual(conteo_cierre.cantidad, 6)
        self.assertEqual(conteo_cierre.diferencia_piezas, 1)

        stock = StockBilleteCaja.objects.get(caja=caja_obj, denominacion=d100)
        self.assertEqual(stock.cantidad, 6)



