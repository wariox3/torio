import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0029_contacto_campos_requeridos'),
    ]

    operations = [
        migrations.AddField(
            model_name='ctnmovimiento',
            name='contacto',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='movimientos',
                to='contenedor.ctncontacto',
            ),
        ),
        migrations.AlterField(
            model_name='ctnmovimiento',
            name='contacto',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='movimientos',
                to='contenedor.ctncontacto',
            ),
        ),
    ]
