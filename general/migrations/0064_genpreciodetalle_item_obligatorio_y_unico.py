import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0063_genparametro_gen_certificado_vence'),
    ]

    operations = [
        migrations.AlterField(
            model_name='genpreciodetalle',
            name='item',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='precios_detalles_item_rel',
                to='general.genitem',
            ),
        ),
        migrations.AddConstraint(
            model_name='genpreciodetalle',
            constraint=models.UniqueConstraint(
                fields=('precio', 'item'),
                name='gen_precio_detalle_precio_item_unico',
            ),
        ),
    ]
