import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0022_suscripcion_frecuencia_requerida'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CtnEventoPasarela',
            new_name='CtnEventoPago',
        ),
        migrations.AlterModelTable(
            name='ctneventopago',
            table='ctn_evento_pago',
        ),
        migrations.AlterModelOptions(
            name='ctneventopago',
            options={
                'verbose_name': 'Evento pago',
                'verbose_name_plural': 'Eventos pago',
            },
        ),
        migrations.AlterField(
            model_name='ctneventopago',
            name='movimiento',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='eventos_pago',
                to='contenedor.ctnmovimiento',
            ),
        ),
    ]
