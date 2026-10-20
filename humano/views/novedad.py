from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from humano.models import HumNovedad
from humano.serializers import (
    HumNovedadExportarSerializer,
    HumNovedadImportarSerializer,
    HumNovedadSeleccionarSerializer,
    HumNovedadSerializer,
)
from humano.servicios import novedad as servicio_novedad
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]


@extend_schema(tags=['Novedad'])
class HumNovedadViewSet(
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
    serializer_class = HumNovedadSerializer
    serializer_class_exportar = HumNovedadExportarSerializer
    serializer_class_importar = HumNovedadImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = HumNovedad.objects.select_related(
            *HumNovedadSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)

        return qs

    def _guardar_y_liquidar(self, serializer):
        # Una novedad que no se puede liquidar no se guarda: pagaría cero.
        with transaction.atomic():
            novedad = serializer.save()
            try:
                servicio_novedad.liquidar(novedad)
            except servicio_novedad.NovedadError as e:
                raise ValidationError({'detail': e.detail})

    def perform_create(self, serializer):
        self._guardar_y_liquidar(serializer)

    def perform_update(self, serializer):
        self._guardar_y_liquidar(serializer)

    @extend_schema(
        request=inline_serializer('NovedadLiquidarRequest', {'id': serializers.IntegerField()}),
        responses=HumNovedadSerializer,
    )
    @action(detail=False, methods=['post'], url_path='liquidar')
    def liquidar(self, request):
        """Vuelve a liquidar una novedad, p. ej. después de cambiar el salario del contrato."""
        novedad_id = request.data.get('id')
        if not novedad_id:
            return Response({'detail': 'El campo id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            novedad = self.get_queryset().get(pk=novedad_id)
        except (HumNovedad.DoesNotExist, ValueError, TypeError):
            raise NotFound('Novedad no encontrada.')
        try:
            servicio_novedad.liquidar(novedad)
        except servicio_novedad.NovedadError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HumNovedadSerializer(novedad).data, status=status.HTTP_200_OK)

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumNovedadSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumNovedad.objects.select_related('contrato__contacto', 'novedad_tipo').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumNovedadSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
