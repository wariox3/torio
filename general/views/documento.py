from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento
from general.serializers import (
    GenDocumentoCrearSerializer,
    GenDocumentoDetalleVistaSerializer,
    GenDocumentoExportarSerializer,
    GenDocumentoGenerarSerializer,
    GenDocumentoImportarSerializer,
    GenDocumentoSerializer,
)
from general.servicios import generar_documentos
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin


@extend_schema(tags=['Documento'])
class GenDocumentoViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
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

    def update(self, request, *args, **kwargs):
        instancia = self.get_object()
        if not instancia.es_mutable():
            raise ValidationError('El documento no es modificable.')
        return super().update(request, *args, **kwargs)

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

    @extend_schema(request=GenDocumentoGenerarSerializer, responses=GenDocumentoSerializer(many=True))
    @action(detail=False, methods=['post'])
    def generar(self, request):
        serializer = GenDocumentoGenerarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        generados = generar_documentos(
            documento_tipo_origen=datos['documento_tipo_id'],
            documento_tipo_destino_id=datos['documento_tipo_id_destino'].pk,
            fecha=datos['fecha'],
            documento_ids=datos.get('documento_ids'),
        )
        salida = GenDocumentoSerializer(generados, many=True)
        return Response(
            {'generados': len(generados), 'documentos': salida.data},
            status=status.HTTP_201_CREATED,
        )
