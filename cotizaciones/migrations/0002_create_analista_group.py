from django.db import migrations


def create_analista_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    # Create group if not exists
    group, created = Group.objects.get_or_create(name='analista_cambiario')
    # Assign add and view permissions for Cotizacion model
    ContentType = apps.get_model('contenttypes', 'ContentType')
    cotizacion_ct, _ = ContentType.objects.get_or_create(app_label='cotizaciones', model='cotizacion')
    perms = Permission.objects.filter(content_type=cotizacion_ct, codename__in=['add_cotizacion', 'view_cotizacion'])
    group.permissions.add(*perms)


def remove_analista_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='analista_cambiario').delete()

class Migration(migrations.Migration):
    dependencies = [
        ('cotizaciones', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_analista_group, reverse_code=remove_analista_group),
    ]
