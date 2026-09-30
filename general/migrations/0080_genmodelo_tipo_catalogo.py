"""
Renombra el tipo de modelo 'F' (Fixture) a 'C' (Catálogo).

Es parte de unificar la nemotecnia del ecosistema, que dejó de decir "fixture": los
modelos y las carpetas de catálogos pasan a llamarse catálogo (`catalogos/`), y las
semillas editables, datos iniciales (`datos_inicial/`). `gen_modelo` vive en cada tenant, así que el `UPDATE` corre en
todos los schemas con el `migrate` de siempre. `general/catalogos/15_modelo.json` ya
trae 'C' para los contenedores nuevos.
"""

from django.db import migrations, models


def a_catalogo(apps, schema_editor):
    apps.get_model('general', 'GenModelo').objects.filter(tipo='F').update(tipo='C')


def a_fixture(apps, schema_editor):
    apps.get_model('general', 'GenModelo').objects.filter(tipo='C').update(tipo='F')


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0079_alter_gendocumento_electronico_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='genmodelo',
            name='tipo',
            field=models.CharField(choices=[('A', 'Administrador'), ('M', 'Movimiento'), ('D', 'Detalle'), ('C', 'Catálogo'), ('S', 'Soporte')], db_default='A', default='A', max_length=1),
        ),
        migrations.RunPython(a_catalogo, a_fixture),
    ]
