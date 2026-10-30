"""
Management command para poblar la base de datos con datos iniciales (Seed).
Totalmente IDEMPOTENTE: puede ejecutarse múltiples veces sin duplicar registros.

Uso:
    python manage.py seed
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from monedas.models import Moneda, DenominacionMoneda
from pagos.models import MetodoPagoSistema
from cotizaciones.models import Cotizacion, Caja
from clientes.models import Cliente


class Command(BaseCommand):
    help = "Puebla la base de datos con datos iniciales (monedas, denominaciones, métodos de pago, cajas, cotizaciones y clientes) de forma idempotente."

    def add_arguments(self, parser):
        parser.add_argument(
            '--idempotent',
            action='store_true',
            help='Flag de compatibilidad (la ejecución es idempotente por defecto).',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">> Iniciando poblacion de datos iniciales (Seed)..."))

        with transaction.atomic():
            self._seed_monedas()
            self._seed_denominaciones()
            self._seed_metodos_pago()
            self._seed_cajas()
            self._seed_cotizaciones()
            self._seed_clientes()

        self.stdout.write(self.style.SUCCESS("[OK] Seed completado exitosamente."))

    def _seed_monedas(self):
        monedas_data = [
            {"siglas": "PYG", "nombre": "Guaraní Paraguayo", "activa": True},
            {"siglas": "USD", "nombre": "Dólar Estadounidense", "activa": True},
            {"siglas": "BRL", "nombre": "Real Brasileño", "activa": True},
            {"siglas": "EUR", "nombre": "Euro", "activa": True},
            {"siglas": "ARS", "nombre": "Peso Argentino", "activa": True},
        ]
        creadas = 0
        for data in monedas_data:
            _, created = Moneda.objects.get_or_create(
                siglas=data["siglas"],
                defaults={"nombre": data["nombre"], "activa": data["activa"]}
            )
            if created:
                creadas += 1
        self.stdout.write(f"  [OK] Monedas: {len(monedas_data)} disponibles ({creadas} nuevas creadas)")

    def _seed_denominaciones(self):
        denominaciones = {
            "PYG": [100000, 50000, 20000, 10000, 5000, 2000],
            "USD": [100, 50, 20, 10, 5, 1],
            "BRL": [200, 100, 50, 20, 10, 5, 2],
            "EUR": [500, 200, 100, 50, 20, 10, 5],
        }
        creadas = 0
        for siglas, cortes in denominaciones.items():
            moneda = Moneda.objects.filter(siglas=siglas).first()
            if not moneda:
                continue
            for corte in cortes:
                _, created = DenominacionMoneda.objects.get_or_create(
                    moneda=moneda,
                    valor=Decimal(corte),
                    defaults={"activo": True}
                )
                if created:
                    creadas += 1
        self.stdout.write(f"  [OK] Denominaciones de billetes verificadas ({creadas} nuevas)")

    def _seed_metodos_pago(self):
        metodos = [
            {
                "nombre": "Efectivo",
                "categoria": MetodoPagoSistema.Categoria.EFECTIVO,
                "icono": "💵",
                "descripcion": "Pago en efectivo en ventanilla de caja",
            },
            {
                "nombre": "Transferencia Bancaria",
                "categoria": MetodoPagoSistema.Categoria.TRANSFERENCIA,
                "icono": "🏦",
                "descripcion": "Transferencia bancaria directa a cuentas habilitadas",
            },
            {
                "nombre": "SIPAP",
                "categoria": MetodoPagoSistema.Categoria.TRANSFERENCIA,
                "icono": "📲",
                "descripcion": "Sistema de Pagos del Paraguay (SIPAP / LBTR)",
            },
            {
                "nombre": "Tarjeta de Débito",
                "categoria": MetodoPagoSistema.Categoria.TARJETA_DEBITO,
                "icono": "💳",
                "descripcion": "Cobro con POS vía tarjeta de débito",
            },
            {
                "nombre": "Tarjeta de Crédito",
                "categoria": MetodoPagoSistema.Categoria.TARJETA_CREDITO,
                "icono": "💳",
                "descripcion": "Cobro con POS vía tarjeta de crédito",
            },
            {
                "nombre": "Stripe / Pago Online",
                "categoria": MetodoPagoSistema.Categoria.DIGITAL,
                "icono": "🌐",
                "descripcion": "Pasarela de pagos digital Stripe (Checkout / Intent)",
            },
        ]
        creados = 0
        for m in metodos:
            _, created = MetodoPagoSistema.objects.get_or_create(
                nombre=m["nombre"],
                defaults={
                    "categoria": m["categoria"],
                    "icono": m["icono"],
                    "descripcion": m["descripcion"],
                    "activo": True,
                }
            )
            if created:
                creados += 1
        self.stdout.write(f"  [OK] Metodos de pago del sistema: {len(metodos)} disponibles ({creados} nuevos)")

    def _seed_cajas(self):
        cajas = [
            {"numero": 1, "nombre": "Caja 1 - Ventanilla Principal", "sucursal": "Casa Central", "activa": True},
            {"numero": 2, "nombre": "Caja 2 - Ventanilla Rápida", "sucursal": "Casa Central", "activa": True},
            {"numero": 3, "nombre": "Caja 3 - Atención VIP", "sucursal": "Sucursal Villa Morra", "activa": True},
        ]
        creadas = 0
        for c in cajas:
            _, created = Caja.objects.get_or_create(
                numero=c["numero"],
                defaults={
                    "nombre": c["nombre"],
                    "sucursal": c["sucursal"],
                    "activa": c["activa"],
                }
            )
            if created:
                creadas += 1
        self.stdout.write(f"  [OK] Cajas de atencion fisica: {len(cajas)} verificadas ({creadas} nuevas)")

    def _seed_cotizaciones(self):
        pyg = Moneda.objects.filter(siglas="PYG").first()
        if not pyg:
            return

        pares = [
            ("USD", Decimal("7450.00"), Decimal("7550.00")),
            ("EUR", Decimal("8100.00"), Decimal("8250.00")),
            ("BRL", Decimal("1350.00"), Decimal("1420.00")),
            ("ARS", Decimal("6.50"), Decimal("7.50")),
        ]
        creadas = 0
        for siglas_origen, compra, venta in pares:
            moneda_origen = Moneda.objects.filter(siglas=siglas_origen).first()
            if not moneda_origen:
                continue
            # Solo creamos la cotización inicial si no existe una activa para este par
            cotiz_existente = Cotizacion.objects.filter(
                moneda_origen=moneda_origen,
                moneda_destino=pyg,
                activo=True
            ).first()
            if not cotiz_existente:
                Cotizacion.objects.create(
                    moneda_origen=moneda_origen,
                    moneda_destino=pyg,
                    compra=compra,
                    venta=venta,
                    activo=True,
                )
                creadas += 1
        self.stdout.write(f"  [OK] Cotizaciones cambiarias verificadas ({creadas} nuevas)")

    def _seed_clientes(self):
        metodos_activos = list(MetodoPagoSistema.objects.filter(activo=True))

        clientes_data = [
            {
                "tipo_persona": Cliente.TipoPersona.FISICA,
                "segmento": Cliente.Segmento.MINORISTA,
                "documento": "4567890",
                "nombre": "Juan",
                "apellido": "Pérez González",
                "email": "juan.perez@example.com",
                "telefono": "+595 981 123456",
                "direccion": "Av. Mariscal López 1234, Asunción",
            },
            {
                "tipo_persona": Cliente.TipoPersona.FISICA,
                "segmento": Cliente.Segmento.VIP,
                "documento": "1234567",
                "nombre": "María",
                "apellido": "Gómez Benítez",
                "email": "maria.gomez@example.com",
                "telefono": "+595 971 654321",
                "direccion": "Av. Santa Teresa 2500, Asunción",
            },
            {
                "tipo_persona": Cliente.TipoPersona.JURIDICA,
                "segmento": Cliente.Segmento.CORPORATIVO,
                "documento": "80012345-6",
                "razon_social": "Acme Import & Export S.A.",
                "email": "finanzas@acme.com.py",
                "telefono": "+595 21 600700",
                "direccion": "Av. Aviadores del Chaco 2050, WTC Torre 2, Asunción",
            },
        ]
        creados = 0
        for cdata in clientes_data:
            cliente, created = Cliente.objects.get_or_create(
                documento=cdata["documento"],
                defaults=cdata,
            )
            if created:
                creados += 1
                if metodos_activos:
                    cliente.metodos_pago_sistema.set(metodos_activos)
        self.stdout.write(f"  [OK] Clientes demo: {len(clientes_data)} verificados ({creados} nuevos)")
