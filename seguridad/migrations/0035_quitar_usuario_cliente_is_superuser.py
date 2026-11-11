from django.db import migrations


def superusuarios_a_administrador(apps, schema_editor):
    # Lo que daba `is_superuser` lo dan ahora `propietario`, `administrador` y
    # `soporte`. Una membresía con `is_superuser` y sin ninguna de esas marcas
    # (un UPDATE manual) pasa a `administrador` para no perder lo que tenía.
    SegUsuarioCliente = apps.get_model('seguridad', 'SegUsuarioCliente')
    SegUsuarioCliente.objects.filter(
        is_superuser=True, propietario=False, soporte=False,
    ).update(administrador=True)


class Migration(migrations.Migration):

    dependencies = [
        ('seguridad', '0034_usuario_cliente_administrador'),
    ]

    operations = [
        migrations.RunPython(superusuarios_a_administrador, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='segusuariocliente',
            name='is_superuser',
        ),
    ]
