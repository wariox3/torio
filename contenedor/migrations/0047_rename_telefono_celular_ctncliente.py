from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0046_remove_ctninvitacion_rol'),
    ]

    operations = [
        migrations.RenameField(
            model_name='ctncliente',
            old_name='telefono',
            new_name='celular',
        ),
        migrations.AlterField(
            model_name='ctncliente',
            name='celular',
            field=models.CharField(max_length=20, verbose_name='Celular'),
        ),
    ]
