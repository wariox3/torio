from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0024_alter_movimiento'),
    ]

    operations = [
        migrations.RenameField(
            model_name='ctnmovimiento',
            old_name='fecha_emision',
            new_name='fecha',
        ),
        migrations.RenameField(
            model_name='ctnmovimiento',
            old_name='fecha_vencimiento',
            new_name='fecha_vence',
        ),
    ]
