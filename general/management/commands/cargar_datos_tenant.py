import json
from collections import defaultdict
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
    BASE_DIR / 'turno' / 'fixtures',
]

# Carpetas con datos semilla que se siembran únicamente al crear el tenant
# (semántica get_or_create: nunca sobreescriben ediciones del tenant).
# El orden de la lista define el orden de carga entre módulos: contabilidad
# antes que general porque hay FKs cross-módulo (p.ej. GenSede -> ConCentroCosto).
FIXTURES_INICIAL_DIRS = [
    BASE_DIR / 'contabilidad' / 'fixtures_inicial',
    BASE_DIR / 'general' / 'fixtures_inicial',
    BASE_DIR / 'humano' / 'fixtures_inicial',
    BASE_DIR / 'turno' / 'fixtures_inicial',
]


class Command(BaseCommand):
    help = 'Carga datos de referencia en los schemas de tenants (idempotente)'

    # Filas por sentencia. Postgres admite 65.535 parámetros por consulta, así que el
    # tope real depende del ancho de la tabla; 500 deja margen de sobra para la más
    # ancha de los fixtures.
    TAMANO_LOTE = 500

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

        if solo_crear:
            creados, omitidos = self._sembrar(modelo, contenido['data'])
        else:
            creados, actualizados = self._volcar(modelo, contenido['data'])

        # Los fixtures_inicial/ insertan ids explícitos en tablas con secuencia
        # (AutoField); hay que avanzar la secuencia o el próximo INSERT del ORM
        # colisiona con el id ya sembrado.
        if actualizar_secuencia or inicial:
            self._resetear_secuencia(modelo)

        if solo_crear:
            self.stdout.write(
                f'  {archivo.name} ({contenido["model"]}) — creados: {creados}, omitidos: {omitidos}'
            )
        else:
            self.stdout.write(
                f'  {archivo.name} ({contenido["model"]}) — creados: {creados}, actualizados: {actualizados}'
            )

    @staticmethod
    def _sembrar(modelo, filas):
        """
        Semillas editables por el tenant (`fixtures_inicial/`): fila por fila con
        `get_or_create`, que nunca sobreescribe y sí dispara los signals de auditoría.

        Son ocho filas en total, así que volcarlas en bloque no ahorraría nada y en
        cambio perdería las dos propiedades de arriba: `GenContacto` lleva
        `log_auditoria = True` y el contacto sembrado tiene que quedar en `gen_log`.
        """
        creados = omitidos = 0
        for fila in filas:
            datos = dict(fila)
            pk = datos.pop('id')
            _, nuevo = modelo.objects.get_or_create(id=pk, defaults=datos)
            if nuevo:
                creados += 1
            else:
                omitidos += 1
        return creados, omitidos

    def _volcar(self, modelo, filas):
        """
        Catálogos (`fixtures/`): un `INSERT ... ON CONFLICT DO UPDATE` por lote en vez
        de un `update_or_create` por fila.

        Son 4.550 filas en 46 archivos: fila por fila eran 9.000 consultas cada vez que
        se crea un tenant, dentro del request que lo crea. En bloque son 283.

        `bulk_create` no dispara signals, y acá da igual: ningún modelo de catálogo
        declara `log_auditoria` —solo lo hacen `GenContacto` y `GenDocumento`—, y el
        único contacto sembrado va por `_sembrar`.
        """
        ids = [fila['id'] for fila in filas]
        existentes = modelo.objects.filter(pk__in=ids).count()

        # Las filas de un mismo archivo no siempre traen las mismas claves (p.ej.
        # `11_documento_tipo.json` tiene diecinueve formas distintas). Se agrupan por
        # conjunto de claves para que `update_fields` sea el exacto de cada grupo: con
        # la unión, una fila que omite una columna la sobreescribiría con el default
        # del modelo, y el `update_or_create(defaults=...)` anterior no hacía eso.
        nombre_de = {f.attname: f.name for f in modelo._meta.concrete_fields}
        grupos = defaultdict(list)
        for fila in filas:
            grupos[frozenset(fila) - {'id'}].append(fila)

        for claves, grupo in grupos.items():
            objetos = [modelo(**fila) for fila in grupo]
            if claves:
                modelo.objects.bulk_create(
                    objetos,
                    update_conflicts=True,
                    # El fixture nombra las FK por su columna (`estado_id`) y
                    # `update_fields` espera el nombre del campo (`estado`).
                    update_fields=[nombre_de.get(clave, clave) for clave in claves],
                    unique_fields=[modelo._meta.pk.name],
                    batch_size=self.TAMANO_LOTE,
                )
            else:
                # Fila que solo trae el id: no hay nada que actualizar.
                modelo.objects.bulk_create(
                    objetos, ignore_conflicts=True, batch_size=self.TAMANO_LOTE,
                )

        return len(ids) - existentes, existentes

    def _resetear_secuencia(self, modelo):
        tabla = modelo._meta.db_table
        pk_col = modelo._meta.pk.column
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_get_serial_sequence(%s, %s)', [tabla, pk_col])
            secuencia = cursor.fetchone()[0]
            if not secuencia:
                # PK manual sin secuencia (p.ej. BigIntegerField); nada que ajustar.
                return
            cursor.execute(
                f"SELECT setval('{secuencia}', COALESCE(MAX({pk_col}), 1)) FROM {tabla}"
            )
