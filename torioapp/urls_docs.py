"""
Rutas de la documentación OpenAPI (drf-spectacular).

Hay dos schemas, uno por urlconf: el público (login, MFA, contenedor) y el de cada
contenedor. El generador lee `ROOT_URLCONF` e ignora el `request.urlconf` que pone
`TenantHeaderMiddleware`, así que cada vista recibe su `urlconf` explícito.

Los dos se montan en el urlconf **público**, en prefijos distintos: navegar con el
browser no permite mandar `X-Tenant`, y sin ese header la petición cae siempre al
schema público. Si el de contenedor viviera solo en `urls_tenant`, nadie podría
abrirlo desde el navegador.
"""
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

PUBLICO = {
    'urlconf': 'torioapp.urls_public',
    'titulo': 'Torio API — Público',
    'descripcion': (
        'Rutas del schema público: autenticación, MFA y gestión de contenedores. '
        'Se consumen **sin** el header `X-Tenant`.'
    ),
}

CONTENEDOR = {
    'urlconf': 'torioapp.urls_tenant',
    'titulo': 'Torio API — Contenedor',
    'descripcion': (
        'Rutas que sirve el schema de cada contenedor. Todas exigen el header '
        '`X-Tenant` con el nombre del schema; sin él la petición cae al schema '
        'público y la ruta no existe.'
    ),
}


def rutas(schema, prefijo='api/', sufijo=''):
    """Las tres rutas (schema, swagger, redoc) de uno de los dos schemas."""
    nombre_schema = f'schema{sufijo}'
    return [
        path(
            f'{prefijo}schema/',
            SpectacularAPIView.as_view(
                urlconf=schema['urlconf'],
                custom_settings={
                    'TITLE': schema['titulo'],
                    'DESCRIPTION': schema['descripcion'],
                },
            ),
            name=nombre_schema,
        ),
        path(
            f'{prefijo}docs/',
            SpectacularSwaggerView.as_view(url_name=nombre_schema),
            name=f'swagger-ui{sufijo}',
        ),
        path(
            f'{prefijo}redoc/',
            SpectacularRedocView.as_view(url_name=nombre_schema),
            name=f'redoc{sufijo}',
        ),
    ]
