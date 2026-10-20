from datetime import date

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from general.models import GenDocumento
from general.serializers import (
    GenDocumentoCarteraCorteInformeExportarSerializer,
    GenDocumentoCarteraCorteInformeSerializer,
    GenDocumentoInformeExportarSerializer,
    GenDocumentoInformeSerializer,
    GenDocumentoNominaInformeExportarSerializer,
    GenDocumentoNominaInformeSerializer,
)
from general.servicios import cartera as cartera_servicio
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin

# Registro de informes sobre GenDocumento.
# Cada informe declara su invariante (`filtro`, garantizada por el servidor). Las
# columnas las aporta el serializer estándar; un informe puede sobreescribirlas
# con `serializer` / `exportar` si lo necesita. Un informe con `corte` es la
# cartera de ese lado a una fecha: no filtra, la arma `cartera.corte` con la
# `fecha` que manda el cliente.
INFORMES = {
    'cobrar_pendiente': {
        'filtro': Q(
            pendiente__gt=0,
            documento_tipo__cobrar=True,
            estado_aprobado=True,
            estado_anulado=False,
        ),
    },
    'pagar_pendiente': {
        'filtro': Q(
            pendiente__gt=0,
            documento_tipo__pagar=True,
            estado_aprobado=True,
            estado_anulado=False,
        ),
    },
    'cobrar_corte': {
        'corte': 'cobrar',
        'serializer': GenDocumentoCarteraCorteInformeSerializer,
        'exportar': GenDocumentoCarteraCorteInformeExportarSerializer,
    },
    'pagar_corte': {
        'corte': 'pagar',
        'serializer': GenDocumentoCarteraCorteInformeSerializer,
        'exportar': GenDocumentoCarteraCorteInformeExportarSerializer,
    },
    # Todas las nóminas, aprobadas o no: así se revisa una programación generada
    # antes de aprobarla. El estado queda como filtro (`estado_aprobado`).
    'nomina': {
        'filtro': Q(documento_tipo__documento_clase_id=701),  # Nómina
        'serializer': GenDocumentoNominaInformeSerializer,
        'exportar': GenDocumentoNominaInformeExportarSerializer,
    },
}


@extend_schema(tags=['Informe: Documento'])
class GenDocumentoInformeViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    viewsets.GenericViewSet,
):
    """
    Punto único de informes sobre GenDocumento.

    El informe se elige con el parámetro `informe` (body o query string). Cada
    informe define en `INFORMES` su invariante (filtro garantizado por el
    servidor) y, opcionalmente, su serializer de columnas.

        POST /lista/    { "informe": "...", "filtros": [...] }
        POST /excel/    { "informe": "...", "filtros": [...] }

    Los de cartera al corte (`cobrar_corte`, `pagar_corte`) piden además
    `fecha` (AAAA-MM-DD), la del corte.
    """

    def _informe(self):
        # Generación de esquema (drf-spectacular): no hay request real, no filtrar.
        if getattr(self, 'swagger_fake_view', False):
            return {'filtro': Q()}

        request = getattr(self, 'request', None)
        clave = None
        if request is not None:
            try:
                clave = request.data.get('informe')
            except Exception:
                clave = None
            if not clave:
                clave = request.query_params.get('informe')
        if not clave:
            raise ValidationError({'informe': 'Este campo es requerido.'})
        if clave not in INFORMES:
            raise ValidationError(
                {'informe': f'Informe "{clave}" no existe. Opciones: {sorted(INFORMES)}.'}
            )
        return INFORMES[clave]

    def get_serializer_class(self):
        return self._informe().get('serializer', GenDocumentoInformeSerializer)

    def get_serializer_exportar(self):
        return self._informe().get('exportar', GenDocumentoInformeExportarSerializer)()

    def _parametro(self, nombre):
        """Un parámetro del body o, si no viene, de la query string."""
        try:
            valor = self.request.data.get(nombre)
        except Exception:
            valor = None
        return valor or self.request.query_params.get(nombre)

    def _fecha_corte(self):
        valor = self._parametro('fecha')
        if not valor:
            raise ValidationError({'fecha': 'Este campo es requerido para la cartera al corte.'})
        try:
            return date.fromisoformat(str(valor))
        except ValueError:
            raise ValidationError({'fecha': 'Debe ser una fecha AAAA-MM-DD.'})

    def get_queryset(self):
        informe = self._informe()
        if 'corte' in informe:
            return cartera_servicio.corte(informe['corte'], self._fecha_corte())
        return GenDocumento.objects.filter(informe['filtro'])
