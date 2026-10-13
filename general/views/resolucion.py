from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
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
    OpenApiParameter('venta', bool, description='Solo las resoluciones de venta'),
    OpenApiParameter('compra', bool, description='Solo las resoluciones de compra'),
]


class ResolucionesValidarRequestSerializer(serializers.Serializer):
    venta = serializers.BooleanField(
        required=False, allow_null=True, default=None,
        help_text='Limita el proceso a las resoluciones de venta (true) o a las que no lo son (false).',
    )
    compra = serializers.BooleanField(
        required=False, allow_null=True, default=None,
        help_text='Limita el proceso a las resoluciones de compra (true) o a las que no lo son (false).',
    )


class ResolucionImportarDianRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(
        help_text='Id de la resolución en el servicio de facturación electrónica.',
    )


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
        if request.query_params.get('venta') in ('true', 'True', '1'):
            qs = qs.filter(venta=True)
        if request.query_params.get('compra') in ('true', 'True', '1'):
            qs = qs.filter(compra=True)
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(numero__icontains=search) | qs.filter(prefijo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenResolucionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Listar las resoluciones del servicio de facturación electrónica',
        description=(
            'Las resoluciones que el servicio de facturación electrónica tiene del '
            'emisor de la empresa, que son las que se pueden traer con '
            '`importar-dian` usando su `id`. El emisor no se manda: sale de '
            '`gen_rededoc_emisor`.\n\n'
            'Responde 200 con `count` y `results`, paginado de a 10; `page` pide '
            'otra página. Si la empresa no tiene emisor configurado responde 404.'
        ),
        parameters=[OpenApiParameter('page', int, description='Número de página')],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='lista-dian')
    def lista_dian(self, request):
        pagina = request.query_params.get('page')
        if pagina is not None and not (pagina.isdigit() and int(pagina) > 0):
            return Response(
                {'detail': 'El parámetro page debe ser un número entero mayor que cero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            datos = factura_electronica_servicio.resoluciones_consultar(pagina and int(pagina))
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Importar una resolución desde el servicio de facturación electrónica',
        description=(
            'Crea la resolución que el servicio de facturación electrónica tiene con '
            'ese `id`, ya traída de la DIAN, y la deja con `estado_validado` en '
            'verdadero. Queda como de compra si es de documento soporte y como de '
            'venta en los demás casos.\n\n'
            'Responde 201 con la resolución creada. Si la empresa ya tiene una con el '
            'mismo número y prefijo responde 400 con el motivo en `detail`; si la '
            'empresa no tiene emisor, o la resolución no existe o no es de su emisor, '
            '404.'
        ),
        request=ResolucionImportarDianRequestSerializer,
        responses={201: GenResolucionSerializer},
    )
    @action(detail=False, methods=['post'], url_path='importar-dian')
    def importar_dian(self, request):
        resolucion_id = request.data.get('id')
        if isinstance(resolucion_id, bool) or not str(resolucion_id or '').isdigit():
            return Response(
                {'detail': 'El campo id es requerido y debe ser un número entero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            resolucion = factura_electronica_servicio.resolucion_importar(int(resolucion_id))
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(GenResolucionSerializer(resolucion).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Validar las resoluciones en la DIAN',
        description=(
            'Valida contra la DIAN, a través del servicio de facturación '
            'electrónica, las resoluciones vigentes de la empresa, y marca como '
            'inactivas las que ya vencieron. El emisor no se manda: sale de '
            '`gen_rededoc_emisor`. Con `venta` o `compra` el proceso se limita a las '
            'resoluciones de un módulo: cada uno filtra por su campo, en `true` o en '
            '`false`; sin ninguno se procesan todas.\n\n'
            'Cada resolución vigente queda con `estado_validado` según lo que '
            'responda el servicio. Responde 200 con `inactivadas`, `validadas` y '
            '`resoluciones`: una entrada por resolución enviada, con su `id`, '
            '`validado`, `inconsistencia` (el rango o la vigencia no coinciden) y '
            'los datos registrados en la DIAN.\n\n'
            'Si la empresa no tiene emisor configurado responde 404; si el emisor '
            'no tiene un software aceptado por la DIAN, o la DIAN no devuelve '
            'rangos, 400 con el motivo en `detail`, y no se cambia nada.'
        ),
        request=ResolucionesValidarRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'], url_path='validar-dian')
    def validar_dian(self, request):
        serializer = ResolucionesValidarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            datos = factura_electronica_servicio.resoluciones_validar(
                serializer.validated_data['venta'], serializer.validated_data['compra'],
            )
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(datos, status=status.HTTP_200_OK)
