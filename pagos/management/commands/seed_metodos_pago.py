"""
Management command: seed_metodos_pago
Carga los métodos de pago estáticos del sistema en la base de datos.
Uso: python manage.py seed_metodos_pago
"""
from django.core.management.base import BaseCommand
from pagos.models import MetodoPagoSistema


METODOS_INICIALES = [
    {
        'nombre': 'Efectivo (Guaranies)',
        'categoria': MetodoPagoSistema.Categoria.EFECTIVO,
        'icono': 'GS',
        'descripcion': 'Pago en efectivo en moneda local (PYG - Guaranies paraguayos).',
    },
    {
        'nombre': 'Efectivo (Dolares USD)',
        'categoria': MetodoPagoSistema.Categoria.EFECTIVO,
        'icono': 'USD',
        'descripcion': 'Pago en efectivo en dolares americanos.',
    },
    {
        'nombre': 'Efectivo (Euros EUR)',
        'categoria': MetodoPagoSistema.Categoria.EFECTIVO,
        'icono': 'EUR',
        'descripcion': 'Pago en efectivo en euros.',
    },
    {
        'nombre': 'Efectivo (Reales BRL)',
        'categoria': MetodoPagoSistema.Categoria.EFECTIVO,
        'icono': 'BRL',
        'descripcion': 'Pago en efectivo en reales brasileros.',
    },
    {
        'nombre': 'Tarjeta de Credito Visa',
        'categoria': MetodoPagoSistema.Categoria.TARJETA_CREDITO,
        'icono': 'TC',
        'descripcion': 'Tarjeta de credito Visa.',
    },
    {
        'nombre': 'Tarjeta de Credito Mastercard',
        'categoria': MetodoPagoSistema.Categoria.TARJETA_CREDITO,
        'icono': 'TC',
        'descripcion': 'Tarjeta de credito Mastercard.',
    },
    {
        'nombre': 'Tarjeta de Debito',
        'categoria': MetodoPagoSistema.Categoria.TARJETA_DEBITO,
        'icono': 'TD',
        'descripcion': 'Tarjeta de debito bancaria (cualquier banco).',
    },
    {
        'nombre': 'Transferencia Bancaria (SIPAP)',
        'categoria': MetodoPagoSistema.Categoria.TRANSFERENCIA,
        'icono': 'TB',
        'descripcion': (
            'Transferencia interbancaria via SIPAP (Sistema de Pagos del Paraguay). '
            'El cliente adjunta comprobante para verificacion manual.'
        ),
    },
    {
        'nombre': 'Transferencia Internacional (SWIFT)',
        'categoria': MetodoPagoSistema.Categoria.TRANSFERENCIA,
        'icono': 'TI',
        'descripcion': 'Transferencia bancaria internacional via SWIFT/SEPA.',
    },
    {
        'nombre': 'Stripe (Pago Online)',
        'categoria': MetodoPagoSistema.Categoria.DIGITAL,
        'icono': 'ST',
        'descripcion': 'Pago digital seguro a traves de la plataforma Stripe con tarjeta.',
    },
    {
        'nombre': 'Billetera Digital (Ueno / Tigo Money)',
        'categoria': MetodoPagoSistema.Categoria.DIGITAL,
        'icono': 'BD',
        'descripcion': 'Pago mediante billetera digital local (Ueno, Tigo Money, etc.).',
    },
]


class Command(BaseCommand):
    help = 'Carga el catalogo inicial de metodos de pago del sistema (MetodoPagoSistema).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Elimina y recrea todos los metodos de pago del sistema.',
        )

    def handle(self, *args, **options):
        if options['reset']:
            MetodoPagoSistema.objects.all().delete()
            self.stdout.write(self.style.WARNING('Catalogo de metodos de pago eliminado.'))

        creados = 0
        actualizados = 0
        for datos in METODOS_INICIALES:
            nombre = datos.pop('nombre')
            obj, created = MetodoPagoSistema.objects.update_or_create(
                nombre=nombre,
                defaults=datos,
            )
            datos['nombre'] = nombre  # Restaurar para no mutar el dict
            if created:
                creados += 1
                self.stdout.write(f'  [NUEVO] {obj}')
            else:
                actualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seed completado: {creados} creados, {actualizados} ya existian. '
            f'Total: {MetodoPagoSistema.objects.count()} metodos en el sistema.'
        ))
