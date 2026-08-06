"""
Rutas de `seguridad` que se sirven DENTRO del schema de cada contenedor.

Casi todo lo de `seguridad` (login, usuarios, membresías) vive en el schema
público, en `seguridad/urls.py`. Acá va lo que necesita el tenant ya resuelto
porque consulta tablas que existen una vez por schema, como
`permissions_usertenantpermissions`.

Se incluye desde `torioapp/urls_tenant.py`, que es el ROOT_URLCONF: cuando llega
el header `X-Tenant`, `TenantHeaderMiddleware` no toca `request.urlconf`, así que
la petición se resuelve contra este urlconf. Sin el header, el middleware fuerza
`PUBLIC_SCHEMA_URLCONF` y estas rutas no existen — por eso las vistas de acá
pueden dar por hecho que `request.tenant` es un contenedor real.
"""

from rest_framework.routers import DefaultRouter

from seguridad.views import SegUsuarioClientePermisoViewSet

router = DefaultRouter()
router.register(
    r'usuario-cliente-permiso',
    SegUsuarioClientePermisoViewSet,
    basename='usuario-cliente-permiso',
)

urlpatterns = router.urls
