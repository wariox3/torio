"""
La aplicación de Celery de torio. El broker es RabbitMQ (`CELERY_BROKER_URL`).

Como `manage.py`, arranca con los settings de desarrollo salvo que se diga otra
cosa, así que en local basta con:

    celery -A torioapp worker -l info -Q notificar_documento,celery

En producción los fija la unidad systemd (`Environment=DJANGO_SETTINGS_MODULE=
torioapp.settings.prod`, ver DESPLIEGUE.md §8.1). Esa línea es obligatoria: sin ella
el worker correría con `DEBUG = True` y el resto de los settings de desarrollo.

Las tareas corren fuera de cualquier request, así que no hay tenant resuelto por
el middleware: cada tarea que toque datos de un tenant recibe su `schema_name` y
entra con `schema_context`. Sin eso correría en el schema público.
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'torioapp.settings.dev')

app = Celery('torioapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
