from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Cotizacion
from .services import simular_conversion, obtener_monedas_disponibles, redondear_monto

User = get_user_model()


class SimuladorConversionServiceTest(TestCase):
    """Pruebas unitarias para el servicio de simulación de conversión (IS2-10)."""

    def setUp(self):
        # Cotización activa USD -> PYG
        self.cot_usd_pyg = Cotizacion.objects.create(
            moneda_origen='USD',
            moneda_destino='PYG',
            compra=Decimal('7500.00'),
            venta=Decimal('7600.00'),
            activo=True
        )
        # Cotización activa BRL -> PYG
        self.cot_brl_pyg = Cotizacion.objects.create(
            moneda_origen='BRL',
            moneda_destino='PYG',
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
            moneda_origen='USD',
            moneda_destino='PYG',
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
        self.cot_usd = Cotizacion.objects.create(
            moneda_origen='USD',
            moneda_destino='PYG',
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
