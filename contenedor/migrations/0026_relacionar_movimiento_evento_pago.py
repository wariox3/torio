import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0025_rename_fechas_movimiento'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ctneventopago',
            name='movimiento',
        ),
        migrations.RemoveField(
            model_name='ctnmovimiento',
            name='numero',
        ),
        migrations.AddField(
            model_name='ctnmovimiento',
            name='evento_pago',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='movimiento',
                to='contenedor.ctneventopago',
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='ctnmovimiento',
            name='evento_pago',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='movimiento',
                to='contenedor.ctneventopago',
            ),
        ),
    ]
