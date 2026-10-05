from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from humano.formatos import FormatoAporte
from humano.models import HumAporte
from humano.serializers import (
    HumAporteExportarSerializer,
    HumAporteImportarSerializer,
    HumAporteSeleccionarSerializer,
    HumAporteSerializer,
)
from humano.servicios import (
    AporteError,
    PilaError,
    aprobar_aporte,
    cargar_contratos_aporte,
    desaprobar_aporte,
    desgenerar_aporte,
    generar_aporte,
    generar_plano,
    recalcular_entidades,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('estado_aprobado', bool, description='Filtrar por aprobado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por año'),
]


class AporteRequestSerializer(serializers.Serializer):
    aporte_id = serializers.IntegerField()


@extend_schema(tags=['Aporte'])
class HumAporteViewSet(
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
    serializer_class = HumAporteSerializer
    serializer_class_exportar = HumAporteExportarSerializer
    serializer_class_importar = HumAporteImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = HumAporte.objects.select_related(
            *HumAporteSerializer.select_related_lista
        ).order_by('-id')

        valor = self.request.query_params.get('estado_aprobado')
        if valor is not None:
            qs = qs.filter(estado_aprobado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumAporteSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumAporte.objects.order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(anio__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumAporteSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=AporteRequestSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['post'], url_path='cargar-contrato')
    def cargar_contrato(self, request):
        """Agrega los contratos de la sucursal vigentes en el mes, con su IBC de la nómina aprobada."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.get(pk=serializer.validated_data['aporte_id'])
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        try:
            creados = cargar_contratos_aporte(aporte)
        except AporteError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        aporte.refresh_from_db(fields=['contratos', 'empleados'])
        return Response(
            {'creados': creados, 'contratos': aporte.contratos, 'empleados': aporte.empleados},
            status=status.HTTP_200_OK,
        )

    @extend_schema(request=AporteRequestSerializer, responses=HumAporteSerializer)
    @action(detail=False, methods=['post'], url_path='generar')
    def generar(self, request):
        """Liquida el aporte: líneas por contrato y novedad, totales y lo que se le debe a cada entidad."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.get(pk=serializer.validated_data['aporte_id'])
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        try:
            aporte = generar_aporte(aporte)
        except AporteError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumAporteSerializer(aporte).data, status=status.HTTP_200_OK)

    @extend_schema(request=AporteRequestSerializer, responses=HumAporteSerializer)
    @action(detail=False, methods=['post'], url_path='generar-entidad')
    def generar_entidad(self, request):
        """Vuelve a calcular lo que se le debe a cada entidad desde los detalles del aporte."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.get(pk=serializer.validated_data['aporte_id'])
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        try:
            aporte = recalcular_entidades(aporte)
        except AporteError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumAporteSerializer(aporte).data, status=status.HTTP_200_OK)

    @extend_schema(request=AporteRequestSerializer, responses=HumAporteSerializer)
    @action(detail=False, methods=['post'], url_path='desgenerar')
    def desgenerar(self, request):
        """Borra los detalles y las entidades del aporte y deja sus totales en cero."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.get(pk=serializer.validated_data['aporte_id'])
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        try:
            aporte = desgenerar_aporte(aporte)
        except AporteError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumAporteSerializer(aporte).data, status=status.HTTP_200_OK)

    @extend_schema(request=AporteRequestSerializer, responses=HumAporteSerializer)
    @action(detail=False, methods=['post'], url_path='aprobar')
    def aprobar(self, request):
        """Crea y aprueba un documento de seguridad social por entidad."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.get(pk=serializer.validated_data['aporte_id'])
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        try:
            aporte = aprobar_aporte(aporte)
        except AporteError as e:
            return Response({'detail': e.detail, 'errores': e.errores}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumAporteSerializer(aporte).data, status=status.HTTP_200_OK)

    @extend_schema(request=AporteRequestSerializer, responses=HumAporteSerializer)
    @action(detail=False, methods=['post'], url_path='desaprobar')
    def desaprobar(self, request):
        """Borra los documentos de seguridad social, si ninguno tiene egreso ni está contabilizado."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.get(pk=serializer.validated_data['aporte_id'])
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        try:
            aporte = desaprobar_aporte(aporte)
        except AporteError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumAporteSerializer(aporte).data, status=status.HTTP_200_OK)

    @extend_schema(request=AporteRequestSerializer, responses={(200, 'text/plain'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'], url_path='plano-operador')
    def plano_operador(self, request):
        """El archivo plano de la PILA para subir al operador de información."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.select_related('sucursal', 'entidad_riesgo').get(
                pk=serializer.validated_data['aporte_id'],
            )
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        try:
            contenido, nombre = generar_plano(aporte)
        except PilaError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(contenido, content_type='text/plain; charset=windows-1252')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    @extend_schema(request=AporteRequestSerializer, responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'], url_path='imprimir')
    def imprimir(self, request):
        """Resumen del aporte en PDF: una fila por línea con sus días, IBC y cotizaciones."""
        serializer = AporteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            aporte = HumAporte.objects.select_related('sucursal').get(pk=serializer.validated_data['aporte_id'])
        except HumAporte.DoesNotExist:
            raise NotFound('Aporte no encontrado.')

        contenido, nombre = FormatoAporte(aporte).pdf()
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{nombre}"'
        return response
