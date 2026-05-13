from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0028_contacto_numero_identificacion_requerido'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ctncontacto',
            name='direccion',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='ctncontacto',
            name='telefono',
            field=models.CharField(max_length=50),
        ),
    ]
