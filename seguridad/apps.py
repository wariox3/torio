from django.apps import AppConfig


class SeguridadConfig(AppConfig):
    name = 'seguridad'

    def ready(self):
        from seguridad.signals import conectar
        conectar()
