from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenResolucion
from general.serializers import (
    GenResolucionExportarSerializer,
    GenResolucionImportarSerializer,
    GenResolucionSeleccionarSerializer,
    GenResolucionSerializer,
)
from general.servicios import factura_electronica as factura_electronica_servicio
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por número o prefijo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por número o prefijo'),
]


@extend_schema(tags=['Resolución'])
class GenResolucionViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenResolucionSerializer
    serializer_class_exportar = GenResolucionExportarSerializer
    serializer_class_importar = GenResolucionImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = GenResolucion.objects.order_by('numero')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(numero__icontains=search) | qs.filter(prefijo__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenResolucionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenResolucion.objects.order_by('numero')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(numero__icontains=search) | qs.filter(prefijo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenResolucionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Validar las resoluciones en la DIAN',
        description=(
            'Valida contra la DIAN, a través del servicio de facturación '
            'electrónica, las resoluciones vigentes de la empresa, y marca como '
            'inactivas las que ya vencieron. No recibe nada: el emisor sale de '
            '`gen_rededoc_emisor`.\n\n'
            'Cada resolución vigente queda con `estado_validado` según lo que '
            'responda el servicio. Responde 200 con `inactivadas`, `validadas` y '
            '`resoluciones`: una entrada por resolución enviada, con su `id`, '
            '`validado`, `inconsistencia` (el rango o la vigencia no coinciden) y '
            'los datos registrados en la DIAN.\n\n'
            'Si la empresa no tiene emisor configurado responde 404; si el emisor '
            'no tiene un software aceptado por la DIAN, o la DIAN no devuelve '
            'rangos, 400 con el motivo en `detail`, y no se cambia nada.'
        ),
        request=None,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'], url_path='validar-resoluciones')
    def validar_resoluciones(self, request):
        try:
            datos = factura_electronica_servicio.resoluciones_validar()
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(datos, status=status.HTTP_200_OK)
