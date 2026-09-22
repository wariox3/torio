"""
ASGI config for torioapp project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Desarrollo por defecto, como `manage.py` y `celery.py`. En producción lo fija
# la unidad systemd (`Environment=DJANGO_SETTINGS_MODULE=torioapp.settings.prod`,
# DESPLIEGUE.md §8): esa línea es obligatoria.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'torioapp.settings.dev')

application = get_asgi_application()
