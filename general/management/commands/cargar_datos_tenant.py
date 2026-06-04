import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context

from contenedor.models import CtnCliente

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

FIXTURES_DIRS = [
    BASE_DIR / 'general' / 'fixtures',
    BASE_DIR / 'contabilidad' / 'fixtures',
    BASE_DIR / 'humano' / 'fixtures',
]


class Command(BaseCommand):
    help = 'Carga datos de referencia en los schemas de tenants (idempotente)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            type=str,
            help='Cargar solo en un schema específico (por defecto todos los tenants)',
        )

    def handle(self, *args, **options):
        archivos = sorted(f for d in FIXTURES_DIRS for f in d.glob('*.json'))
        if not archivos:
            self.stdout.write(self.style.WARNING('No se encontraron archivos JSON en fixtures/'))
            return

        schema = options.get('schema')
        tenants = (
            CtnCliente.objects.filter(schema_name=schema)
            if schema
            else CtnCliente.objects.exclude(schema_name='public')
        )

        for tenant in tenants:
            self.stdout.write(f'\n=== {tenant.schema_name} ({tenant.nombre}) ===')
            with schema_context(tenant.schema_name):
                for archivo in archivos:
                    self._cargar(archivo)

    def _cargar(self, archivo: Path):
        contenido = json.loads(archivo.read_text(encoding='utf-8'))
        modelo = apps.get_model(contenido['model'])
        actualizar_secuencia = contenido.get('actualizar_secuencia', False)

        creados = actualizados = 0
        for item in contenido['data']:
            pk = item.pop('id')
            _, nuevo = modelo.objects.update_or_create(id=pk, defaults=item)
            if nuevo:
                creados += 1
            else:
                actualizados += 1

        if actualizar_secuencia:
            self._resetear_secuencia(modelo)

        self.stdout.write(
            f'  {archivo.name} ({contenido["model"]}) — creados: {creados}, actualizados: {actualizados}'
        )

    def _resetear_secuencia(self, modelo):
        tabla = modelo._meta.db_table
        pk_col = modelo._meta.pk.column
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{tabla}', '{pk_col}'), "
                f"COALESCE(MAX({pk_col}), 1)) FROM {tabla}"
            )
