"""
La aplicación de Celery de torio. El broker es RabbitMQ (`CELERY_BROKER_URL`).

Como `wsgi.py`, arranca con los settings de producción salvo que se diga otra
cosa: el worker es un proceso de producción igual que gunicorn. En desarrollo:

    DJANGO_SETTINGS_MODULE=torioapp.settings.dev celery -A torioapp worker -l info

Las tareas corren fuera de cualquier request, así que no hay tenant resuelto por
el middleware: cada tarea que toque datos de un tenant recibe su `schema_name` y
entra con `schema_context`. Sin eso correría en el schema público.
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'torioapp.settings.prod')

app = Celery('torioapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
