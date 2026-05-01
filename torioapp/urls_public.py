from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Rutas que sirve el schema público (gestión de tenants, super-admin, etc.).
urlpatterns = [
    path('admin/', admin.site.urls),
    path('contenedor/', include('contenedor.urls')),
    path('seguridad/', include('seguridad.urls')),

    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
