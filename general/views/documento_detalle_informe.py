from decimal import Decimal

from django.db.models import Q, Sum
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from general.models import GenDocumentoDetalle
from general.serializers import (
    GenDocumentoDetallePendienteFacturarExportarSerializer,
    GenDocumentoDetallePendienteFacturarSerializer,
)
from utilidades.filtros import aplicar_filtros
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin
from utilidades.mixins.filtros import BusquedaRequest

# Registro de informes sobre GenDocumentoDetalle.
# Para agregar uno: crea su serializer (columnas) + exportar y registra aquí su
# invariante (`filtro`, garantizada por el servidor) y los campos a totalizar.
INFORMES = {
    'pendiente_facturar': {
        'serializer': GenDocumentoDetallePendienteFacturarSerializer,
        'exportar': GenDocumentoDetallePendienteFacturarExportarSerializer,
        'filtro': Q(pendiente__gt=0),
        'totales': ('cantidad', 'total', 'afectado', 'pendiente'),
    },
}

_INFORME_DEFAULT = 'pendiente_facturar'


@extend_schema(tags=['Informe: Documento detalle'])
class GenDocumentoDetalleInformeViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    viewsets.GenericViewSet,
):
    """
    Punto único de informes sobre GenDocumentoDetalle.

    El informe se elige con el parámetro `informe` (body o query string). Cada
    informe define en `INFORMES` su invariante (filtro garantizado por el
    servidor), columnas (serializer) y campos de totales.

        POST /lista/    { "informe": "...", "filtros": [...] }
        POST /excel/    { "informe": "...", "filtros": [...] }
        POST /totales/  { "informe": "...", "filtros": [...] }
    """

    def _informe(self):
        # Generación de esquema (drf-spectacular): no hay request real, usar default.
        if getattr(self, 'swagger_fake_view', False):
            return INFORMES[_INFORME_DEFAULT]

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
        return self._informe()['serializer']

    def get_serializer_exportar(self):
        return self._informe()['exportar']()

    def get_queryset(self):
        return GenDocumentoDetalle.objects.filter(self._informe()['filtro'])

    @extend_schema(summary='Totales del informe', request=BusquedaRequest)
    @action(detail=False, methods=['post'])
    def totales(self, request):
        informe = self._informe()
        filtros = request.data.get('filtros') or []
        qs = aplicar_filtros(
            self.get_queryset(), filtros, informe['serializer'].campos_filtrables,
        )
        agregados = qs.aggregate(**{campo: Sum(campo) for campo in informe['totales']})
        cero = Decimal('0')
        return Response({clave: (valor or cero) for clave, valor in agregados.items()})
