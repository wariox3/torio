from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from humano.formatos import FormatoLiquidacion
from humano.models import HumLiquidacion, HumLiquidacionAdicional
from humano.serializers import (
    HumLiquidacionExportarSerializer,
    HumLiquidacionImportarSerializer,
    HumLiquidacionSeleccionarSerializer,
    HumLiquidacionSerializer,
)
from humano.servicios import (
    LiquidacionError,
    aprobar_liquidacion,
    desaprobar_liquidacion,
    desgenerar_liquidacion,
    generar_liquidacion,
    liquidar,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
    OpenApiParameter('estado_aprobado', bool, description='Filtrar por aprobado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]


class LiquidacionRequestSerializer(serializers.Serializer):
    liquidacion_id = serializers.IntegerField()


@extend_schema(tags=['Liquidación'])
class HumLiquidacionViewSet(
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
    serializer_class = HumLiquidacionSerializer
    serializer_class_exportar = HumLiquidacionExportarSerializer
    serializer_class_importar = HumLiquidacionImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = HumLiquidacion.objects.select_related(
            *HumLiquidacionSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)

        valor = self.request.query_params.get('estado_aprobado')
        if valor is not None:
            qs = qs.filter(estado_aprobado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumLiquidacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumLiquidacion.objects.select_related('contrato__contacto').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumLiquidacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        liquidacion = self.get_object()
        if liquidacion.estado_generado or liquidacion.estado_aprobado:
            return Response(
                {'detail': 'La liquidación está generada o aprobada: desgenérela antes de eliminarla.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Los adicionales son parte de la liquidación: se van con ella.
        with transaction.atomic():
            HumLiquidacionAdicional.objects.filter(liquidacion=liquidacion).delete()
            liquidacion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=LiquidacionRequestSerializer, responses=HumLiquidacionSerializer)
    @action(detail=False, methods=['post'], url_path='reliquidar')
    def reliquidar(self, request):
        """Vuelve a calcular las prestaciones con el salario y los últimos pagos actuales del contrato."""
        serializer = LiquidacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            liquidacion = HumLiquidacion.objects.get(pk=serializer.validated_data['liquidacion_id'])
        except HumLiquidacion.DoesNotExist:
            raise NotFound('Liquidación no encontrada.')

        try:
            liquidacion = liquidar(liquidacion)
        except LiquidacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumLiquidacionSerializer(liquidacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=LiquidacionRequestSerializer, responses=HumLiquidacionSerializer)
    @action(detail=False, methods=['post'], url_path='generar')
    def generar(self, request):
        """Crea el documento de la liquidación: una línea por prestación y por adicional."""
        serializer = LiquidacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            liquidacion = HumLiquidacion.objects.get(pk=serializer.validated_data['liquidacion_id'])
        except HumLiquidacion.DoesNotExist:
            raise NotFound('Liquidación no encontrada.')

        try:
            liquidacion = generar_liquidacion(liquidacion)
        except LiquidacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumLiquidacionSerializer(liquidacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=LiquidacionRequestSerializer, responses=HumLiquidacionSerializer)
    @action(detail=False, methods=['post'], url_path='desgenerar')
    def desgenerar(self, request):
        """Borra el documento de la liquidación."""
        serializer = LiquidacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            liquidacion = HumLiquidacion.objects.get(pk=serializer.validated_data['liquidacion_id'])
        except HumLiquidacion.DoesNotExist:
            raise NotFound('Liquidación no encontrada.')

        try:
            liquidacion = desgenerar_liquidacion(liquidacion)
        except LiquidacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumLiquidacionSerializer(liquidacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=LiquidacionRequestSerializer, responses=HumLiquidacionSerializer)
    @action(detail=False, methods=['post'], url_path='aprobar')
    def aprobar(self, request):
        """Aprueba el documento de la liquidación: toma consecutivo y queda por pagar."""
        serializer = LiquidacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            liquidacion = HumLiquidacion.objects.get(pk=serializer.validated_data['liquidacion_id'])
        except HumLiquidacion.DoesNotExist:
            raise NotFound('Liquidación no encontrada.')

        try:
            liquidacion = aprobar_liquidacion(liquidacion)
        except LiquidacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumLiquidacionSerializer(liquidacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=LiquidacionRequestSerializer, responses=HumLiquidacionSerializer)
    @action(detail=False, methods=['post'], url_path='desaprobar')
    def desaprobar(self, request):
        """Quita el aprobado del documento, si no tiene egreso ni está contabilizado."""
        serializer = LiquidacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            liquidacion = HumLiquidacion.objects.get(pk=serializer.validated_data['liquidacion_id'])
        except HumLiquidacion.DoesNotExist:
            raise NotFound('Liquidación no encontrada.')

        try:
            liquidacion = desaprobar_liquidacion(liquidacion)
        except LiquidacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumLiquidacionSerializer(liquidacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=LiquidacionRequestSerializer, responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'], url_path='imprimir')
    def imprimir(self, request):
        """La liquidación en PDF, con las firmas del empleado y la empresa."""
        serializer = LiquidacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            liquidacion = HumLiquidacion.objects.select_related(
                'contrato__contacto__banco', 'contrato__grupo', 'contrato__motivo_terminacion',
            ).get(pk=serializer.validated_data['liquidacion_id'])
        except HumLiquidacion.DoesNotExist:
            raise NotFound('Liquidación no encontrada.')

        contenido, nombre = FormatoLiquidacion(liquidacion).pdf()
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{nombre}"'
        return response
