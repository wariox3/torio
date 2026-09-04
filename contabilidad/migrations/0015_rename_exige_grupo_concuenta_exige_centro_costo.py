from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0014_alter_conperiodo_anio_alter_conperiodo_id_and_more'),
    ]

    operations = [
        # Rename y no drop + add: la columna ya tiene datos en los tenants.
        migrations.RenameField(
            model_name='concuenta',
            old_name='exige_grupo',
            new_name='exige_centro_costo',
        ),
    ]
