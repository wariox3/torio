from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento, GenDocumentoDetalle
from general.serializers import GenDocumentoDetalleSerializer, GenDocumentoSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Documento'])
class GenDocumentoViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenDocumentoSerializer

    campos_filtrables = {
        'id', 'numero', 'fecha', 'documento_tipo_id', 'contacto_id',
        'estado_aprobado', 'estado_anulado', 'estado_contabilizado',
    }
    select_related_lista = ('documento_tipo', 'contacto')
    prefetch_related_lista = ('documentos_detalles_documento_rel',)
    ordenamiento_default_lista = ('-fecha', '-numero')

    def get_queryset(self):
        return GenDocumento.objects.select_related(
            'documento_tipo', 'contacto',
        ).prefetch_related(
            'documentos_detalles_documento_rel',
        )

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

    @action(
        detail=True,
        methods=['patch', 'delete'],
        url_path=r'detalle/(?P<detalle_id>[^/.]+)',
    )
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
