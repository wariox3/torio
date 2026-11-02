"""
Pasa las aplicaciones de la cuenta (`SegUsuarioAplicacion`, que 0031 borra) a cada
membresía (`SegUsuarioClienteAplicacion`): toda membresía normal recibe las que su
usuario tiene hoy, y una de soporte las recibe todas.
"""
from django.db import migrations


def pasar_aplicaciones(apps, schema_editor):
    CtnAplicacion = apps.get_model('contenedor', 'CtnAplicacion')
    SegUsuarioAplicacion = apps.get_model('seguridad', 'SegUsuarioAplicacion')
    SegUsuarioCliente = apps.get_model('seguridad', 'SegUsuarioCliente')
    SegUsuarioClienteAplicacion = apps.get_model('seguridad', 'SegUsuarioClienteAplicacion')

    todas = list(CtnAplicacion.objects.values_list('id', flat=True))
    por_usuario = {}
    for usuario_id, aplicacion_id in SegUsuarioAplicacion.objects.values_list('usuario_id', 'aplicacion_id'):
        por_usuario.setdefault(usuario_id, []).append(aplicacion_id)

    filas = []
    for membresia_id, usuario_id, soporte in SegUsuarioCliente.objects.values_list('id', 'usuario_id', 'soporte'):
        aplicaciones = todas if soporte else por_usuario.get(usuario_id, [])
        filas.extend(
            SegUsuarioClienteAplicacion(usuario_cliente_id=membresia_id, aplicacion_id=aplicacion_id)
            for aplicacion_id in aplicaciones
        )
    SegUsuarioClienteAplicacion.objects.bulk_create(filas, ignore_conflicts=True, batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ('seguridad', '0029_usuario_cliente_aplicacion'),
    ]

    operations = [
        migrations.RunPython(pasar_aplicaciones, migrations.RunPython.noop),
    ]
