"""
Pasa los `acceso_*` de cada membresía (`SegUsuarioCliente`) a las aplicaciones de
la cuenta (`SegUsuarioAplicacion`), antes de que 0028 borre esos campos.

Los accesos eran por contenedor y las aplicaciones son por usuario: cada usuario
queda con las que tenía en `True` en **cualquiera** de sus membresías, sin contar
las de soporte (esas tenían todo). Un usuario sin membresías propias arranca con
todas, como uno nuevo.

Crea las filas de `CtnAplicacion` porque el catálogo se carga después de
`migrate` (`cargar_geodata`) y sin ellas los FK fallarían; los mismos valores que
`contenedor/catalogos/10_aplicacion.json`.
"""
from django.db import migrations

APLICACIONES = {
    1: 'Venta', 2: 'Compra', 3: 'Cartera', 4: 'Tesorería',
    5: 'Contabilidad', 6: 'Inventario', 7: 'Humano', 8: 'Turno',
}

APLICACION_POR_ACCESO = {
    'acceso_venta': 1,
    'acceso_compra': 2,
    'acceso_cartera': 3,
    'acceso_tesoreria': 4,
    'acceso_contabilidad': 5,
    'acceso_inventario': 6,
    'acceso_humano': 7,
    'acceso_turno': 8,
}


def pasar_accesos(apps, schema_editor):
    CtnAplicacion = apps.get_model('contenedor', 'CtnAplicacion')
    SegUsuario = apps.get_model('seguridad', 'SegUsuario')
    SegUsuarioCliente = apps.get_model('seguridad', 'SegUsuarioCliente')
    SegUsuarioAplicacion = apps.get_model('seguridad', 'SegUsuarioAplicacion')

    for aplicacion_id, nombre in APLICACIONES.items():
        CtnAplicacion.objects.update_or_create(id=aplicacion_id, defaults={'nombre': nombre})

    por_usuario = {}
    membresias = SegUsuarioCliente.objects.filter(soporte=False).values(
        'usuario_id', *APLICACION_POR_ACCESO,
    )
    for membresia in membresias:
        aplicaciones = por_usuario.setdefault(membresia['usuario_id'], set())
        aplicaciones.update(
            aplicacion_id for campo, aplicacion_id in APLICACION_POR_ACCESO.items()
            if membresia[campo]
        )

    filas = []
    for usuario_id in SegUsuario.objects.values_list('id', flat=True):
        aplicaciones = por_usuario.get(usuario_id, set(APLICACIONES))
        filas.extend(
            SegUsuarioAplicacion(usuario_id=usuario_id, aplicacion_id=aplicacion_id)
            for aplicacion_id in aplicaciones
        )
    SegUsuarioAplicacion.objects.bulk_create(filas, ignore_conflicts=True, batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0057_ctnpendientetipo_aplicacion'),
        ('seguridad', '0026_usuario_aplicacion_unico'),
    ]

    operations = [
        migrations.RunPython(pasar_accesos, migrations.RunPython.noop),
    ]
