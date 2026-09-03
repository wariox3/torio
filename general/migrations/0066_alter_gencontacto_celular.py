"""
`GenContacto.celular` pasa a admitir NULL y deja de ser obligatorio.

El campo se creó como `CharField(default='', db_default='')`, así que "sin celular"
se guardaba como cadena vacía. Al permitir NULL habría dos formas de decir lo mismo
—`''` y `NULL`—, y un filtro por `celular__isnull` se saltaría las filas viejas, así
que las que ya estaban en `''` se normalizan a NULL en la misma migración.
"""

from django.db import migrations, models


def vaciar_a_null(apps, schema_editor):
    GenContacto = apps.get_model('general', 'GenContacto')
    GenContacto.objects.filter(celular='').update(celular=None)


def revertir(apps, schema_editor):
    """Al volver a NOT NULL la columna no admite NULL: se devuelven a `''`."""
    GenContacto = apps.get_model('general', 'GenContacto')
    GenContacto.objects.filter(celular__isnull=True).update(celular='')


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0065_genparametro_gen_asistente_datos_iniciales'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gencontacto',
            name='celular',
            field=models.CharField(max_length=50, null=True),
        ),
        migrations.RunPython(vaciar_a_null, revertir),
    ]
