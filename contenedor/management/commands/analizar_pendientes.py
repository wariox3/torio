import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from contabilidad.servicios import pendiente as pendiente_contabilidad
from contenedor.models import CtnCliente, CtnPendiente

logger = logging.getLogger(__name__)

# Id de `CtnPendienteTipo` → detector. Un pendiente nuevo es una fila en
# `contenedor/catalogos/11_pendiente_tipo.json`, su función en el
# `servicios/pendiente.py` del módulo dueño de la data y una entrada acá. Cada
# detector recibe `hoy`, corre dentro del schema del tenant y devuelve
# `(cantidad, mensaje)` o `None`.
DETECTORES = {
    1: pendiente_contabilidad.periodo_anterior_abierto,
}


class Command(BaseCommand):
    help = (
        'Recorre los contenedores listos con suscripción vigente y deja en '
        'ctn_pendiente lo que cada uno tiene pendiente.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str,
            help='Analizar solo un contenedor (por defecto todos).',
        )

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        # Mismo criterio que `SuscripcionVigente`: fecha_fin = hoy sigue vigente.
        # Uno en `creando` o `error` puede no tener tablas.
        clientes = CtnCliente.objects.exclude(schema_name='public').filter(
            estado=CtnCliente.ESTADO_LISTO,
            suscripcion__fecha_fin__gte=hoy,
        ).order_by('id')
        if options.get('schema'):
            clientes = clientes.filter(schema_name=options['schema'])

        analizados = creados = 0
        fallidos = []
        for cliente in clientes:
            try:
                encontrados = self._detectar(cliente, hoy)
            except Exception:
                # Sin tocar sus pendientes: mejor los de la corrida anterior que ninguno.
                logger.exception('analizar_pendientes: falló %s', cliente.schema_name)
                fallidos.append(cliente.schema_name)
                continue

            # Fuera del schema y en una transacción: el usuario nunca ve el
            # contenedor sin pendientes mientras se reemplazan.
            with transaction.atomic():
                CtnPendiente.objects.filter(cliente=cliente).delete()
                CtnPendiente.objects.bulk_create([
                    CtnPendiente(
                        cliente=cliente, pendiente_tipo_id=tipo_id,
                        cantidad=cantidad, mensaje=mensaje,
                    )
                    for tipo_id, cantidad, mensaje in encontrados
                ])
            analizados += 1
            creados += len(encontrados)
            self.stdout.write(f'{cliente.schema_name}: {len(encontrados)} pendientes')

        self.stdout.write(self.style.SUCCESS(
            f'Analizados: {analizados}, pendientes: {creados}, con error: {len(fallidos)}'
        ))
        if fallidos:
            self.stdout.write(self.style.ERROR('Con error: ' + ', '.join(fallidos)))

    @staticmethod
    def _detectar(cliente, hoy):
        encontrados = []
        with schema_context(cliente.schema_name):
            for tipo_id, detector in DETECTORES.items():
                resultado = detector(hoy)
                if resultado:
                    cantidad, mensaje = resultado
                    encontrados.append((tipo_id, cantidad, mensaje))
        return encontrados
