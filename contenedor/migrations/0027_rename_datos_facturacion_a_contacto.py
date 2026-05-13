import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0026_relacionar_movimiento_evento_pago'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CtnDatosFacturacion',
            new_name='CtnContacto',
        ),
        migrations.AlterModelTable(
            name='ctncontacto',
            table='ctn_contacto',
        ),
        migrations.AlterModelOptions(
            name='ctncontacto',
            options={'verbose_name': 'Contacto', 'verbose_name_plural': 'Contactos'},
        ),
        migrations.AlterField(
            model_name='ctncontacto',
            name='identificacion',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='contactos',
                to='contenedor.ctnidentificacion',
            ),
        ),
        migrations.AlterField(
            model_name='ctncontacto',
            name='ciudad',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='contactos',
                to='contenedor.ctnciudad',
            ),
        ),
        migrations.AlterField(
            model_name='ctncontacto',
            name='usuario',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='contactos',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
