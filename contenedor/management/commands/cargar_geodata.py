import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand

_BASE = Path(__file__).resolve().parent.parent.parent.parent
FIXTURES_DIRS = [
    _BASE / 'contenedor' / 'fixtures',
    _BASE / 'seguridad' / 'fixtures',
]


class Command(BaseCommand):
    help = 'Carga datos del schema público desde los fixtures/ de contenedor y seguridad (idempotente)'

    def handle(self, *_args, **_options):
        archivos = sorted(
            archivo for d in FIXTURES_DIRS for archivo in d.glob('*.json')
        )
        if not archivos:
            self.stdout.write(self.style.WARNING('No se encontraron archivos JSON en fixtures/'))
            return
        for archivo in archivos:
            self._cargar(archivo)

    def _cargar(self, archivo: Path):
        contenido = json.loads(archivo.read_text(encoding='utf-8'))
        modelo = apps.get_model(contenido['model'])
        datos = contenido['data']
        creados = actualizados = 0
        for item in datos:
            pk = item.pop('id')
            _, nuevo = modelo.objects.update_or_create(id=pk, defaults=item)
            if nuevo:
                creados += 1
            else:
                actualizados += 1
        self.stdout.write(f'{archivo.name} ({contenido["model"]}) — creados: {creados}, actualizados: {actualizados}')
