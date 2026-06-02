from django.conf import settings
from django.contrib import admin
from django.urls import include, path

# Rutas servidas dentro del schema de cada cliente.
urlpatterns = [
    path('admin/', admin.site.urls),
    path('general/', include('general.urls')),
    path('contabilidad/', include('contabilidad.urls')),
]

if settings.ENABLE_API_DOCS:
    from drf_spectacular.views import (
        SpectacularAPIView,
        SpectacularRedocView,
        SpectacularSwaggerView,
    )
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]
