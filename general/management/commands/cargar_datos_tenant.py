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

# Carpetas con datos semilla que se siembran únicamente al crear el tenant
# (semántica get_or_create: nunca sobreescriben ediciones del tenant).
# El orden de la lista define el orden de carga entre módulos: contabilidad
# antes que general porque hay FKs cross-módulo (p.ej. GenSede -> ConCentroCosto).
FIXTURES_INICIAL_DIRS = [
    BASE_DIR / 'contabilidad' / 'fixtures_inicial',
    BASE_DIR / 'general' / 'fixtures_inicial',
    BASE_DIR / 'humano' / 'fixtures_inicial',
]


class Command(BaseCommand):
    help = 'Carga datos de referencia en los schemas de tenants (idempotente)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            type=str,
            help='Cargar solo en un schema específico (por defecto todos los tenants)',
        )
        parser.add_argument(
            '--inicial',
            action='store_true',
            help='Sembrar también los datos iniciales de fixtures_inicial/ '
            '(solo al crear el tenant; nunca sobreescriben ediciones).',
        )

    def handle(self, *args, **options):
        # Primero los catálogos (fixtures/) y luego los datos semilla
        # (fixtures_inicial/), para que estos puedan depender por FK de aquellos.
        archivos = sorted(
            ((f, False) for d in FIXTURES_DIRS for f in d.glob('*.json')),
            key=lambda a: a[0].name,
        )
        if options.get('inicial'):
            # Se cargan módulo por módulo en el orden de FIXTURES_INICIAL_DIRS
            # (no global por nombre) para respetar las FKs cross-módulo;
            # dentro de cada módulo, por nombre de archivo.
            for d in FIXTURES_INICIAL_DIRS:
                archivos += [
                    (f, True) for f in sorted(d.glob('*.json'), key=lambda f: f.name)
                ]
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
                for archivo, inicial in archivos:
                    self._cargar(archivo, inicial)

    def _cargar(self, archivo: Path, inicial: bool = False):
        contenido = json.loads(archivo.read_text(encoding='utf-8'))
        modelo = apps.get_model(contenido['model'])
        actualizar_secuencia = contenido.get('actualizar_secuencia', False)
        # solo_crear: inserta la fila únicamente si no existe y nunca la
        # sobreescribe en ejecuciones posteriores (datos editables por el tenant).
        # Los datos de fixtures_inicial/ siempre se tratan así.
        solo_crear = inicial or contenido.get('solo_crear', False)

        creados = actualizados = omitidos = 0
        for item in contenido['data']:
            pk = item.pop('id')
            if solo_crear:
                _, nuevo = modelo.objects.get_or_create(id=pk, defaults=item)
                if nuevo:
                    creados += 1
                else:
                    omitidos += 1
                continue
            _, nuevo = modelo.objects.update_or_create(id=pk, defaults=item)
            if nuevo:
                creados += 1
            else:
                actualizados += 1

        if actualizar_secuencia:
            self._resetear_secuencia(modelo)

        if solo_crear:
            self.stdout.write(
                f'  {archivo.name} ({contenido["model"]}) — creados: {creados}, omitidos: {omitidos}'
            )
        else:
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
