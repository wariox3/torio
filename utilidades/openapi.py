"""
Ajustes del schema OpenAPI que genera drf-spectacular.
"""
import copy

# urlconf del schema público. Sus rutas se resuelven sin `X-Tenant`, así que el
# parámetro no se documenta ahí.
URLCONF_PUBLICO = 'torioapp.urls_public'

_METODOS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}

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
