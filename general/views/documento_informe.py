from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from general.models import GenDocumento
from general.serializers import (
    GenDocumentoInformeExportarSerializer,
    GenDocumentoInformeSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin

# Registro de informes sobre GenDocumento.
# Cada informe declara su invariante (`filtro`, garantizada por el servidor). Las
# columnas las aporta el serializer estándar; un informe puede sobreescribirlas
# con `serializer` / `exportar` si lo necesita.
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

    def get_queryset(self):
        return GenDocumento.objects.filter(self._informe()['filtro'])
