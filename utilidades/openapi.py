"""
Ajustes del schema OpenAPI que genera drf-spectacular.
"""
import copy

# urlconf del schema público. Sus rutas se resuelven sin `X-Tenant`, así que el
# parámetro no se documenta ahí.
URLCONF_PUBLICO = 'torioapp.urls_public'

_METODOS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}

# Nombre visible de cada app, tomado del primer segmento de la ruta. Redoc pinta
# los grupos en este orden, no alfabéticamente.
APPS = (
    ('general', 'General'),
    ('contabilidad', 'Contabilidad'),
    ('inventario', 'Inventario'),
    ('turno', 'Turno'),
    ('humano', 'Humano'),
    ('seguridad', 'Seguridad'),
    ('contenedor', 'Contenedor'),
)

_PARAMETRO_TENANT = {
    'name': 'X-Tenant',
    'in': 'header',
    'required': True,
    'description': (
        'Nombre del schema del contenedor. Lo resuelve `TenantHeaderMiddleware`: '
        'sin este header la petición cae al schema público y la ruta no existe.'
    ),
    'schema': {'type': 'string'},
}


def agregar_header_tenant(result, generator, request, public):
    """
    Documenta `X-Tenant` en todas las operaciones del schema de tenant.

    Va como postprocessing hook y no como parámetro por vista porque aplica a las
    356 rutas de `urls_tenant` sin excepción. Sin esto, el "Try it out" de Swagger
    sale sin el header, cae al schema público y responde 404.
    """
    if getattr(generator, 'urlconf', None) == URLCONF_PUBLICO:
        return result

    for ruta in result.get('paths', {}).values():
        for metodo, operacion in ruta.items():
            if metodo.lower() not in _METODOS:
                continue
            # Copia por operación: compartir el dict hace que PyYAML emita
            # anchors/aliases (&id001 / *id001) y hay clientes que no los leen.
            operacion.setdefault('parameters', []).append(copy.deepcopy(_PARAMETRO_TENANT))

    return result


def agrupar_tags_por_app(result, generator, request, public):
    """
    Agrupa los tags por aplicación con `x-tagGroups`, que es lo que **Redoc** usa
    para armar las secciones del menú lateral.

    Los tags se dejan intactos —uno por recurso, como los declara cada viewset—
    porque son los que el generador de cliente TypeScript usa para nombrar sus
    servicios. Acá solo se dice a qué app pertenece cada uno, deduciéndolo del
    primer segmento de la ruta. Swagger UI ignora la extensión y sigue plano.
    """
    nombres = dict(APPS)
    grupos = {etiqueta: [] for _, etiqueta in APPS}
    vistos = set()

    for ruta, item in result.get('paths', {}).items():
        app = nombres.get(ruta.strip('/').split('/')[0])
        if app is None:
            continue
        for metodo, operacion in item.items():
            if metodo.lower() not in _METODOS:
                continue
            for tag in operacion.get('tags') or []:
                # Un tag solo puede vivir en un grupo: gana la primera app que lo
                # usa, así que dos apps no deberían compartir el nombre de un tag.
                if tag in vistos:
                    continue
                vistos.add(tag)
                grupos[app].append(tag)

    result['x-tagGroups'] = [
        {'name': etiqueta, 'tags': sorted(grupos[etiqueta])}
        for _, etiqueta in APPS
        if grupos[etiqueta]
    ]
    return result
