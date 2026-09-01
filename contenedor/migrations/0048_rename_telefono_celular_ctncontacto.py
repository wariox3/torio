from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0047_rename_telefono_celular_ctncliente'),
    ]

    operations = [
        migrations.RenameField(
            model_name='ctncontacto',
            old_name='telefono',
            new_name='celular',
        ),
    ]
