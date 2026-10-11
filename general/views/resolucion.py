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
]


class ResolucionTipoSoftwareRequestSerializer(serializers.Serializer):
    tipo_software = serializers.ChoiceField(
        choices=factura_electronica_servicio.TIPOS_SOFTWARE_RESOLUCION,
        default=factura_electronica_servicio.TIPO_SOFTWARE_RESOLUCION_POR_DEFECTO,
        help_text='Software DIAN del emisor con el que se consultan las resoluciones.',
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
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(numero__icontains=search) | qs.filter(prefijo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenResolucionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Validar una resolución en la DIAN',
        description=(
            'Comprueba, a través del servicio de facturación electrónica, que la '
            'resolución está asociada en la DIAN al emisor de la empresa, y que su '
            'prefijo, rango de consecutivos y vigencia son los que la DIAN autorizó. '
            'El emisor no se manda: sale de `gen_rededoc_emisor`.\n\n'
            'Responde 200 con `estado_validado` y `diferencias`: si todo coincide el '
            'estado queda en verdadero y la lista vacía; si no, queda en falso y la '
            'lista dice qué cambia.\n\n'
            'Si la resolución no existe en la DIAN, o el emisor no tiene software de '
            'ese tipo aceptado, responde 400 con el motivo en `detail` y el estado '
            'no se toca.'
        ),
        request=ResolucionTipoSoftwareRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=True, methods=['post'])
    def validar(self, request, pk=None):
        resolucion = self.get_object()
        serializer = ResolucionTipoSoftwareRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            diferencias = factura_electronica_servicio.resolucion_validar(
                resolucion, serializer.validated_data['tipo_software'],
            )
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(
            {'estado_validado': resolucion.estado_validado, 'diferencias': diferencias},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary='Importar las resoluciones de la DIAN',
        description=(
            'Trae de la DIAN, a través del servicio de facturación electrónica, las '
            'resoluciones del software de ese tipo del emisor de la empresa, y crea '
            'las que no existan (se comparan prefijo y número). Las que ya existen '
            'no se tocan.\n\n'
            'Responde las resoluciones creadas: 201 si creó alguna y 200 con la '
            'lista vacía si no había ninguna nueva. Si la DIAN no devuelve rangos, o '
            'la empresa no tiene software de ese tipo, responde 400 con el motivo '
            'en `detail`.'
        ),
        request=ResolucionTipoSoftwareRequestSerializer,
        responses=GenResolucionSerializer(many=True),
    )
    @action(detail=False, methods=['post'], url_path='importar-dian')
    def importar_dian(self, request):
        serializer = ResolucionTipoSoftwareRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            creadas = factura_electronica_servicio.resolucion_importar_dian(
                serializer.validated_data['tipo_software'],
            )
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(
            GenResolucionSerializer(creadas, many=True).data,
            status=status.HTTP_201_CREATED if creadas else status.HTTP_200_OK,
        )
