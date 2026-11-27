from django.db import transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from contabilidad.models import ConConciliacion, ConConciliacionDetalle
from contabilidad.serializers import (
    ConConciliacionDetalleExportarSerializer,
    ConConciliacionDetalleSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin


@extend_schema(tags=['Conciliación detalle'])
class ConConciliacionDetalleViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ConConciliacionDetalleSerializer
    serializer_class_exportar = ConConciliacionDetalleExportarSerializer

    def get_queryset(self):
        return ConConciliacionDetalle.objects.select_related(
            *ConConciliacionDetalleSerializer.select_related_lista
        )

    def get_queryset_excel(self):
        # El Excel lleva el tipo del documento, que la lista no muestra.
        return self.get_queryset_lista().select_related('documento__documento_tipo')

    @extend_schema(
        summary='Limpiar detalles',
        description=(
            'Borra todos los detalles (movimientos de libros cargados) de la '
            'conciliación, para volver a cargarlos. Si alguno está conciliado no '
            'borra ninguno: hay que desconciliar primero.'
        ),
        request=inline_serializer(
            name='ConciliacionDetalleLimpiarRequest',
            fields={'conciliacion': serializers.IntegerField()},
        ),
        responses=inline_serializer(
            name='ConciliacionDetalleLimpiarResponse',
            fields={'eliminados': serializers.IntegerField()},
        ),
    )
    @action(detail=False, methods=['post'])
    def limpiar(self, request):
        valor = request.data.get('conciliacion')
        if valor in (None, ''):
            raise ValidationError({'conciliacion': 'Este campo es requerido.'})
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValidationError({'conciliacion': f'Debe ser un número (PK), recibido: "{valor}"'})

        with transaction.atomic():
            # Bloquea la conciliación: un `cargar` o un `conciliar` en curso sobre
            # ella termina antes de que se borre, en vez de cruzarse.
            if not ConConciliacion.objects.select_for_update().filter(pk=pk).exists():
                raise NotFound('Conciliación no encontrada.')
            detalles = ConConciliacionDetalle.objects.filter(conciliacion_id=pk)
            conciliados = detalles.filter(estado_conciliado=True).count()
            if conciliados:
                raise ValidationError({
                    'detail': (
                        f'La conciliación tiene {conciliados} '
                        f'{"detalle conciliado" if conciliados == 1 else "detalles conciliados"}. '
                        f'Desconcílielos primero.'
                    ),
                })
            eliminados, _ = detalles.delete()
        return Response({'eliminados': eliminados}, status=status.HTTP_200_OK)
