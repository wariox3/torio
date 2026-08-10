"""
Definición de los grupos de permisos del producto.

Un `Group` de Django es la unidad de autorización: es lo que se asigna al
`UserTenantPermissions` de un usuario dentro de un contenedor y lo único que
`has_perm()` consulta. `SegRol` NO interviene: quedó como etiqueta de
presentación.

Los grupos viven en el schema público y se comparten entre todos los
contenedores; lo que es por tenant es qué grupos tiene asignados cada usuario.

Esta declaración es la fuente de verdad de QUÉ PERMISOS tiene cada grupo.
`python manage.py sincronizar_grupos` la aplica: crea los grupos que falten y
reemplaza sus permisos. No borra grupos que no estén acá, para no pisar los que
se creen desde la administración.

Claves admitidas dentro de cada grupo:
    'app_label'           -> todos los modelos de la app
    'app_label.modelo'    -> solo ese modelo (en minúsculas, como el codename)
"""

TODAS = ('add', 'change', 'delete', 'view')
VER = ('view',)

# {id del Group: (nombre, {objetivo: (acciones,)})}
#
# El id se fija a propósito, igual que en los fixtures JSON del proyecto: es lo
# que el front manda en `grupo_ids` al invitar, y tiene que significar lo mismo
# en desarrollo, en pruebas y en producción. Si se crearan solo por nombre, cada
# entorno les asignaría un id distinto.
GRUPOS = {
    1: ('Venta', {
        'general.gendocumento': TODAS,
        'general.gencontacto': TODAS,
        'general.genitem': TODAS,
        'general.genprecio': TODAS,
        'general.genasesor': TODAS,
        'general.genresolucion': TODAS,
        'general.gencuentabanco': TODAS,
        'general.gensede': TODAS,
        'inventario.invalmacen': TODAS,
    }),
    2: ('Compra', {
        'general.gendocumento': TODAS,
        'general.gencontacto': TODAS,
        'general.genitem': TODAS,
        'general.genresolucion': TODAS,
        'general.genformapago': TODAS,
        'inventario.invalmacen': TODAS,
    }),
    3: ('Tesoreria', {
        'general.gendocumento': TODAS,
        'general.gencuentabanco': TODAS,
        'general.genformapago': TODAS,
    }),
    4: ('Cartera', {
        'general.gendocumento': TODAS,
        'general.gencontacto': TODAS,
        'general.genformapago': VER,
    }),
    5: ('Inventario', {
        'general.gendocumento': TODAS,
        'general.genitem': TODAS,
        'inventario.invalmacen': TODAS,
    }),
    6: ('Humano', {
        'general.gendocumento': TODAS,
        'general.gencontacto': TODAS,
        'humano.humcontrato': TODAS,
        'humano.humcargo': TODAS,
        'humano.humgrupo': TODAS,
        'humano.humsucursal': TODAS,
        'humano.humadicional': TODAS,
        'humano.humcredito': TODAS,
        'humano.humnovedad': TODAS,
        'humano.humliquidacion': TODAS,
        'humano.humaporte': TODAS,
        'humano.humprogramacion': TODAS,
    }),
    7: ('Contabilidad', {
        'general.gendocumento': TODAS,
        'general.gencontacto': TODAS,
        'contabilidad.concuenta': TODAS,
        'contabilidad.concentrocosto': TODAS,
        'contabilidad.conactivo': TODAS,
        'contabilidad.conperiodo': TODAS,
        'contabilidad.conmovimiento': TODAS,
        'contabilidad.conconciliacion': TODAS,
    }),
    8: ('Turno', {
        'general.gendocumento': TODAS,
        'turno.turpuesto': TODAS,
        'turno.turturno': TODAS,
        'turno.tursecuencia': TODAS,
        'turno.turprogramador': TODAS,
        'turno.turprototipo': TODAS,
        'turno.turprogramacion': TODAS,
        'turno.turprogramacionsimulacion': TODAS,
        'turno.tursoporte': TODAS,
    }),
}
