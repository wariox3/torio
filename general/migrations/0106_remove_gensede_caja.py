from django.db import migrations


class Migration(migrations.Migration):
    """Los datos de caja pasan a `VenCaja`; los de la sede no se copian."""

    dependencies = [
        ('general', '0105_gendocumento_turno'),
    ]

    operations = [
        migrations.RemoveField(model_name='gensede', name='caja_placa'),
        migrations.RemoveField(model_name='gensede', name='caja_ubicacion'),
        migrations.RemoveField(model_name='gensede', name='caja_tipo'),
    ]
