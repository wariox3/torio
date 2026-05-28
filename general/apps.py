from django.apps import AppConfig


class GeneralConfig(AppConfig):
    name = 'general'

    def ready(self):
        from django.apps import apps
        from general.signals import registrar_auditoria
        for modelo in apps.get_models():
            if getattr(modelo, 'log_auditoria', False):
                registrar_auditoria(modelo)
