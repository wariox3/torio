from django.conf import settings
from django.contrib import admin
from django.urls import include, path

# Rutas que sirve el schema público (gestión de tenants, super-admin, etc.).
urlpatterns = [
    path('admin/', admin.site.urls),
    path('contenedor/', include('contenedor.urls')),
    path('seguridad/', include('seguridad.urls')),
]

if settings.ENABLE_API_DOCS:
    from torioapp.urls_docs import CONTENEDOR, PUBLICO, rutas

    # Los dos schemas se sirven acá, sin `X-Tenant`, porque es lo único que el
    # navegador puede abrir: /api/docs/ el público y /api/contenedor/docs/ el de tenant.
    urlpatterns += rutas(PUBLICO)
    urlpatterns += rutas(CONTENEDOR, prefijo='api/contenedor/', sufijo='-contenedor')
