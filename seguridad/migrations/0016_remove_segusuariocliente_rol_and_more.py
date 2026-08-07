"""
Reemplaza `SegUsuarioCliente.rol` por el booleano `propietario`.

El FK a `SegRol` era solo una etiqueta de presentación y ya no se llenaba: las
invitaciones dejaron de llevar rol, así que toda membresía nueva nacía con
rol=None. En su lugar queda `propietario`, que marca al dueño del contenedor.

`propietario` entra en False para todas las filas, así que hay que rellenarlo:
la fuente de verdad es `CtnCliente.owner_id`, que sigue existiendo. Sin este
backfill ningún contenedor tendría dueño marcado en su membresía.
"""

from django.db import migrations, models
from django_tenants.utils import get_public_schema_name


def marcar_propietarios(apps, schema_editor):
    """Pone propietario=True en la membresía de quien es owner del contenedor."""
    if schema_editor.connection.schema_name != get_public_schema_name():
        # `seg_usuario_cliente` y `ctn_cliente` viven solo en el schema público;
        # en los demás el search_path las resolvería a las mismas filas y el
        # UPDATE correría una vez por tenant sin necesidad.
        return

    SegUsuarioCliente = apps.get_model('seguridad', 'SegUsuarioCliente')
    SegUsuarioCliente.objects.filter(
        usuario_id=models.F('cliente__owner_id'),
    ).update(propietario=True)


def revertir(apps, schema_editor):
    """Sin vuelta atrás: el rol original no se puede reconstruir desde el booleano."""


class Migration(migrations.Migration):

    dependencies = [
        ('seguridad', '0015_segusuariocliente_acceso_turno_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='segusuariocliente',
            name='rol',
        ),
        migrations.AddField(
            model_name='segusuariocliente',
            name='propietario',
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.RunPython(marcar_propietarios, revertir),
    ]
