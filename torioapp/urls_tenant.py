from django.contrib import admin
from django.urls import path

# Rutas servidas dentro del schema de cada cliente.
urlpatterns = [
    path('admin/', admin.site.urls),
]
