from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento, GenDocumentoDetalle
from general.serializers import (
    GenDocumentoCrearSerializer,
    GenDocumentoDetalleSerializer,
    GenDocumentoDetalleVistaSerializer,
    GenDocumentoExportarSerializer,
    GenDocumentoImportarSerializer,
    GenDocumentoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin


@extend_schema(tags=['Documento'])
class GenDocumentoViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenDocumentoSerializer
    serializer_class_exportar = GenDocumentoExportarSerializer
    serializer_class_importar = GenDocumentoImportarSerializer

    def get_serializer_class(self):
        if self.action == 'create':
            return GenDocumentoCrearSerializer
        if self.action == 'retrieve':
            return GenDocumentoDetalleVistaSerializer
        return GenDocumentoSerializer

    def get_queryset(self):
        select = GenDocumentoSerializer.select_related_lista
        qs = GenDocumento.objects.select_related(*select)
        if self.action == 'retrieve':
            qs = qs.prefetch_related('documentos_detalles_documento_rel')
        return qs

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            try:
                documento = GenDocumento.objects.select_for_update().get(pk=kwargs['pk'])
            except GenDocumento.DoesNotExist:
                raise NotFound('Documento no encontrado.')
            if not documento.es_mutable():
                raise ValidationError('El documento no es modificable.')
            documento.documentos_detalles_documento_rel.all().delete()
            documento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='detalle')
    def agregar_detalle(self, request, pk=None):
        serializer = GenDocumentoDetalleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            try:
                documento = GenDocumento.objects.select_for_update().get(pk=pk)
            except GenDocumento.DoesNotExist:
                raise NotFound('Documento no encontrado.')
            if not documento.es_mutable():
                raise ValidationError('El documento no es modificable.')
            detalle = GenDocumentoDetalle(documento=documento, **serializer.validated_data)
            detalle.calcular()
            detalle.save()
            documento.recalcular_totales()
            documento.save()

        return Response(
            GenDocumentoDetalleSerializer(detalle).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['patch', 'delete'], url_path=r'detalle/(?P<detalle_id>[^/.]+)')
    def modificar_detalle(self, request, pk=None, detalle_id=None):
        with transaction.atomic():
            try:
                documento = GenDocumento.objects.select_for_update().get(pk=pk)
            except GenDocumento.DoesNotExist:
                raise NotFound('Documento no encontrado.')
            if not documento.es_mutable():
                raise ValidationError('El documento no es modificable.')
            try:
                detalle = documento.documentos_detalles_documento_rel.get(pk=detalle_id)
            except GenDocumentoDetalle.DoesNotExist:
                raise NotFound('Detalle no encontrado.')

            if request.method == 'DELETE':
                detalle.delete()
                documento.recalcular_totales()
                documento.save()
                return Response(status=status.HTTP_204_NO_CONTENT)

            serializer = GenDocumentoDetalleSerializer(detalle, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            for campo, valor in serializer.validated_data.items():
                setattr(detalle, campo, valor)
            detalle.calcular()
            detalle.save()
            documento.recalcular_totales()
            documento.save()

        return Response(GenDocumentoDetalleSerializer(detalle).data)
