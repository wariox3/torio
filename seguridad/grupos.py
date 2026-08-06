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

# {nombre del Group: {objetivo: (acciones,)}}
PERMISOS_POR_GRUPO = {
    'Venta': {'general.gencontacto': TODAS},
    'Compra': {'general.gencontacto': TODAS},
}
