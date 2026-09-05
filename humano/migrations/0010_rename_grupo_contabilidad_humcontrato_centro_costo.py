from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('humano', '0009_humcontrato_habilitado_turno'),
    ]

    operations = [
        # RENAME y no remove/add: la columna ya tiene datos y un remove/add los borra.
        migrations.RenameField(
            model_name='humcontrato',
            old_name='grupo_contabilidad',
            new_name='centro_costo',
        ),
    ]
