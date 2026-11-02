import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0056_ctnaplicacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='ctnpendientetipo',
            name='aplicacion',
            # El default solo llena filas que ya existan (5 = Contabilidad, la de
            # «Periodo anterior abierto»); el campo queda sin default.
            field=models.ForeignKey(
                default=5, on_delete=django.db.models.deletion.PROTECT,
                to='contenedor.ctnaplicacion',
            ),
            preserve_default=False,
        ),
    ]
