from django.contrib import admin
from django.urls import path

# Rutas que sirve el schema público (gestión de tenants, super-admin, etc.).
urlpatterns = [
    path('admin/', admin.site.urls),
]
