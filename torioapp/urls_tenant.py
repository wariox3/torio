from django.contrib import admin
from django.urls import include, path

# Rutas servidas dentro del schema de cada cliente.
urlpatterns = [
    path('admin/', admin.site.urls),
    path('general/', include('general.urls')),
]
