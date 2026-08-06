"""
Elimina la tabla django_content_type de los schemas de tenant.

`django.contrib.contenttypes` estaba en TENANT_APPS, así que cada tenant creaba
su propia django_content_type con ids propios. Pero auth_permission vive solo en
`public`. Al resolver un permiso, PostgreSQL une public.auth_permission con la
django_content_type del schema activo; como los ids no coinciden, el `app_label`
sale de una fila que no corresponde y los permisos cuyo desajuste cruza apps se
pierden sin dar error (medido: 8 de 173 en un schema recién creado, y 106 de 120
ids desalineados).

Al borrar la tabla del tenant, el search_path (`<tenant>, public`) la resuelve a
la de `public` y el JOIN vuelve a ser consistente.
"""

from django.db import migrations
from django_tenants.utils import get_public_schema_name


def eliminar_content_type_del_tenant(apps, schema_editor):
    schema = schema_editor.connection.schema_name

    # Guarda de seguridad: `general` es TENANT_APPS-only, así que el router ya
    # impide que esto corra en el schema público. Se comprueba igual porque
    # borrar public.django_content_type sería irreversible.
    if schema == get_public_schema_name():
        raise RuntimeError(
            'Esta migración no debe ejecutarse en el schema público: '
            'borraría la django_content_type compartida.'
        )

    with schema_editor.connection.cursor() as cursor:
        # Sin CASCADE a propósito: si algo llegara a depender de esta tabla,
        # preferimos que falle de forma visible antes que perder datos.
        cursor.execute(f'DROP TABLE IF EXISTS "{schema}".django_content_type')


def revertir(apps, schema_editor):
    """
    No se recrea la tabla: para volver atrás hay que devolver
    'django.contrib.contenttypes' a TENANT_APPS y correr migrate, que la crea.
    """


class Migration(migrations.Migration):
    dependencies = [
        ('general', '0058_gendocumentodetalle_generado'),
    ]

    operations = [
        migrations.RunPython(eliminar_content_type_del_tenant, revertir),
    ]
