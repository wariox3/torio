from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ParseError, UnsupportedMediaType, ValidationError

from general.models import GenDocumentoDetalle
from general.serializers import (
    GenDocumentoDetalleInformeExportarSerializer,
    GenDocumentoDetalleInformeSerializer,
    GenDocumentoDetalleNominaInformeExportarSerializer,
    GenDocumentoDetalleNominaInformeSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin

# Registro de informes sobre GenDocumentoDetalle.
# Cada informe declara su invariante (`filtro`, garantizada por el servidor). Las
# columnas las aporta el serializer estándar; un informe puede sobreescribirlas
# con `serializer` / `exportar` si lo necesita. `titulo` va encima de la tabla
# en el Excel (`ExportarExcelMixin`).
INFORMES = {
    'pendiente_facturar': {
        'titulo': 'Pendiente por facturar',
        'filtro': Q(
            pendiente__gt=0,
            documento__documento_tipo_id=35,
            documento__estado_aprobado=True,
        ),
    },
    # Sin los tipos de operación cero (pedidos, remisiones): son de venta pero no
    # son la venta, que llega con la factura.
    'venta_item': {
        'titulo': 'Ventas por ítem',
        'filtro': Q(
            documento__documento_tipo__venta=True,
            documento__estado_aprobado=True,
            documento__estado_anulado=False,
        ) & ~Q(documento__documento_tipo__operacion=0),
    },
    # Todas las nóminas, aprobadas o no: así se revisa una programación generada
    # antes de aprobarla. El estado queda como filtro (`documento__estado_aprobado`).
    'nomina_detalle': {
        'titulo': 'Detalle de nómina',
        'filtro': Q(documento__documento_tipo__documento_clase_id=701),  # Nómina
        'serializer': GenDocumentoDetalleNominaInformeSerializer,
        'exportar': GenDocumentoDetalleNominaInformeExportarSerializer,
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
    servidor) y, opcionalmente, su serializer de columnas.

        POST /lista/    { "informe": "...", "filtros": [...] }
        POST /excel/    { "informe": "...", "filtros": [...] }
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
            except (ParseError, UnsupportedMediaType, AttributeError):  # body mal formado o que no es un objeto
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
        return self._informe().get('serializer', GenDocumentoDetalleInformeSerializer)

    def get_titulo_excel(self, serializer):
        return self._informe().get('titulo')

    def get_serializer_exportar(self):
        return self._informe().get('exportar', GenDocumentoDetalleInformeExportarSerializer)()

    def get_queryset(self):
        return GenDocumentoDetalle.objects.filter(self._informe()['filtro'])
