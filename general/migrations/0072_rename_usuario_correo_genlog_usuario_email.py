from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0071_gendocumento_contrato_gendocumentodetalle_activo_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='genlog',
            old_name='usuario_correo',
            new_name='usuario_email',
        ),
    ]
