from django.conf import settings
from django.contrib import admin
from django.urls import include, path

# Rutas servidas dentro del schema de cada cliente.
urlpatterns = [
    path('admin/', admin.site.urls),
    path('general/', include('general.urls')),
    path('contabilidad/', include('contabilidad.urls')),
    path('turno/', include('turno.urls')),
    path('humano/', include('humano.urls')),
    path('inventario/', include('inventario.urls')),
    path('seguridad/', include('seguridad.urls_tenant')),
]

if settings.ENABLE_API_DOCS:
    from torioapp.urls_docs import CONTENEDOR, rutas

    urlpatterns += rutas(CONTENEDOR)
