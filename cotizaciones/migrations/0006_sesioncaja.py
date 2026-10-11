# Generated manually for IS2-60 - SesionCaja
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cotizaciones', '0005_operacion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SesionCaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre_caja', models.CharField(default='Caja Principal', max_length=100, verbose_name='Nombre de Caja')),
                ('fecha_apertura', models.DateTimeField(auto_now_add=True, verbose_name='Fecha y Hora de Apertura')),
                ('monto_inicial', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Monto Inicial')),
                ('fecha_cierre', models.DateTimeField(blank=True, null=True, verbose_name='Fecha y Hora de Cierre')),
                ('monto_final_declarado', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name='Monto Final Declarado')),
                ('saldo_esperado', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name='Saldo Esperado')),
                ('diferencia', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name='Diferencia')),
                ('estado', models.CharField(choices=[('ABIERTA', 'Abierta'), ('CERRADA', 'Cerrada')], default='ABIERTA', max_length=10, verbose_name='Estado')),
                ('observaciones', models.TextField(blank=True, default='', verbose_name='Observaciones de Cierre')),
                ('cajero', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='sesiones_caja', to=settings.AUTH_USER_MODEL, verbose_name='Cajero')),
            ],
            options={
                'verbose_name': 'Sesion de Caja',
                'verbose_name_plural': 'Sesiones de Caja',
                'ordering': ['-fecha_apertura'],
            },
        ),
    ]
