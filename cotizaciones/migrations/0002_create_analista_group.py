from django.db import migrations


def create_analista_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    # Create group if not exists
    group, created = Group.objects.get_or_create(name='analista_cambiario')
    # Assign add and view permissions for Cotizacion model
    cotizacion_ct, _ = ContentType.objects.get_or_create(app_label='cotizaciones', model='cotizacion')
    perm_add, _ = Permission.objects.get_or_create(
        codename='add_cotizacion',
        content_type=cotizacion_ct,
        defaults={'name': 'Can add cotizacion'}
    )
    perm_view, _ = Permission.objects.get_or_create(
        codename='view_cotizacion',
        content_type=cotizacion_ct,
        defaults={'name': 'Can view cotizacion'}
    )
    group.permissions.add(perm_add, perm_view)


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
