import django.db.models.deletion
from django.db import migrations, models


def eliminar_programaciones_incompletas(apps, schema_editor):
    """Borra filas sin turno o sin documento_detalle (heredadas del comportamiento
    anterior). Todas tienen horas 0 o no están ligadas a un detalle, así que su
    eliminación no altera las horas de documento_detalle ni de documento."""
    TurProgramacion = apps.get_model('turno', 'TurProgramacion')
    TurProgramacion.objects.filter(
        models.Q(turno__isnull=True) | models.Q(documento_detalle__isnull=True)
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('turno', '0012_turturno_descanso'),
    ]

    operations = [
        migrations.RunPython(
            eliminar_programaciones_incompletas,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='turprogramacion',
            name='documento_detalle',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='programaciones_documento_detalle_rel',
                to='general.gendocumentodetalle',
            ),
        ),
        migrations.AlterField(
            model_name='turprogramacion',
            name='turno',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='programaciones_turno_rel',
                to='turno.turturno',
            ),
        ),
    ]
