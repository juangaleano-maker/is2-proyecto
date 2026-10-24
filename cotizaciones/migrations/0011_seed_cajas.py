from django.db import migrations

def crear_cajas_iniciales(apps, schema_editor):
    Caja = apps.get_model('cotizaciones', 'Caja')
    cajas_data = [
        {'numero': 1, 'nombre': 'Caja 1 - Ventanilla Principal', 'sucursal': 'Casa Central', 'activa': True},
        {'numero': 2, 'nombre': 'Caja 2 - Ventanilla Rápida', 'sucursal': 'Casa Central', 'activa': True},
        {'numero': 3, 'nombre': 'Caja 3 - Atención VIP', 'sucursal': 'Sucursal Villa Morra', 'activa': True},
    ]
    for c in cajas_data:
        Caja.objects.get_or_create(numero=c['numero'], defaults=c)

def revertir_cajas_iniciales(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('cotizaciones', '0010_caja_conteobilletesesion_cantidad_sistema_and_more'),
    ]

    operations = [
        migrations.RunPython(crear_cajas_iniciales, revertir_cajas_iniciales),
    ]
