from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0027_rename_datos_facturacion_a_contacto'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ctncontacto',
            name='numero_identificacion',
            field=models.CharField(max_length=20),
        ),
    ]
