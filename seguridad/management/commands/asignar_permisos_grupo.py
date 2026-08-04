from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

PERMISOS_POR_GRUPO = {
    'Vendedor': [
        ('general', 'gendocumento', ['add', 'change', 'delete', 'view']),
    ],
}


class Command(BaseCommand):
    help = 'Asigna permisos de Django (add/change/delete/view) a los grupos de rol (idempotente)'

    def handle(self, *_args, **_options):
        for nombre_grupo, modelos in PERMISOS_POR_GRUPO.items():
            grupo = Group.objects.get(name=nombre_grupo)
            permisos = []
            for app_label, model, acciones in modelos:
                content_type = ContentType.objects.get(app_label=app_label, model=model)
                permisos += list(
                    Permission.objects.filter(
                        content_type=content_type,
                        codename__in=[f'{accion}_{model}' for accion in acciones],
                    )
                )
            grupo.permissions.set(permisos)
            self.stdout.write(f'{nombre_grupo}: {len(permisos)} permisos asignados')
