from django.core.management.base import BaseCommand

from seguridad.servicios import sincronizar_grupos


class Command(BaseCommand):
    help = (
        'Crea los grupos declarados en seguridad.grupos y reemplaza sus permisos '
        'por los de la declaración (idempotente). No toca las asignaciones de los '
        'usuarios: esas se otorgan al aceptar una invitación.'
    )

    def handle(self, *args, **options):
        for nombre, cantidad in sorted(sincronizar_grupos().items()):
            self.stdout.write(f'{nombre}: {cantidad} permisos')
