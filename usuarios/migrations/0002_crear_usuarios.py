from django.db import migrations


def crear_usuarios_iniciales(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    Usuario.objects.create(
        id=1,
        nombre='Carlos',
        apellido='González',
        email='carlos.gonzalez@globalexchange.com',
        telefono='0981-123456',
        rol='Administrador',
    )
    Usuario.objects.create(
        id=2,
        nombre='Jorge',
        apellido='Ramírez',
        email='jorge.ramirez@globalexchange.com',
        telefono='0971-654321',
        rol='Operador',
    )


def eliminar_usuarios_iniciales(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    Usuario.objects.filter(id__in=[1, 2]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_usuarios_iniciales, eliminar_usuarios_iniciales),
    ]
