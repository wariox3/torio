from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0010_alter_concuenta_codigo'),
    ]

    operations = [
        migrations.RenameField(
            model_name='conactivo',
            old_name='grupo',
            new_name='centro_costo',
        ),
        migrations.RenameField(
            model_name='conmovimiento',
            old_name='grupo',
            new_name='centro_costo',
        ),
    ]
