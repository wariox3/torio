from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from contabilidad.models import ConConciliacion, ConConciliacionSoporte
from contabilidad.serializers import (
    ConConciliacionSoporteExportarSerializer,
    ConConciliacionSoporteImportarSerializer,
    ConConciliacionSoporteSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.throttles import ImportarUsuarioTenantThrottle

_CONCILIACION_PARAM = OpenApiParameter(
    'conciliacion', int, required=True,
    description='Conciliación a la que pertenece el extracto.',
)

_ImportarSoporteRequest = inline_serializer(
    name='ImportarConciliacionSoporteRequest',
    fields={
        'archivo': serializers.FileField(help_text='Archivo .xlsx'),
        'conciliacion': serializers.IntegerField(help_text='Conciliación padre'),
    },
)


@extend_schema(tags=['Conciliación soporte'])
class ConConciliacionSoporteViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ConConciliacionSoporteSerializer
    serializer_class_exportar = ConConciliacionSoporteExportarSerializer

    def get_queryset(self):
        return ConConciliacionSoporte.objects.select_related(
            *ConConciliacionSoporteSerializer.select_related_lista
        )

    def _conciliacion(self):
        """Resuelve la conciliación que manda el front en `conciliacion`."""
        origen = (
            self.request.query_params
            if self.request.method == 'GET'
            else self.request.data
        )
        valor = origen.get('conciliacion')
        if valor in (None, ''):
            raise ValidationError({'conciliacion': 'Este campo es requerido.'})
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValidationError({'conciliacion': f'Debe ser un número (PK), recibido: "{valor}"'})
        conciliacion = ConConciliacion.objects.filter(pk=pk).first()
        if conciliacion is None:
            raise NotFound('Conciliación no encontrada.')
        return conciliacion

    def get_serializer_importar(self):
        return ConConciliacionSoporteImportarSerializer(self._conciliacion())

    @extend_schema(
        summary='Descargar plantilla del extracto bancario',
        description=(
            'Devuelve un archivo .xlsx con las columnas Fecha, Valor y Detalle. El '
            'valor va con signo: positivo entra al banco (débito), negativo sale '
            '(crédito). Las fechas de ejemplo son las de la conciliación.'
        ),
        parameters=[_CONCILIACION_PARAM],
    )
    @action(detail=False, methods=['get'], url_path='importar-ejemplo')
    def importar_ejemplo(self, request):
        return super().importar_ejemplo(request)

    @extend_schema(
        summary='Importar extracto bancario',
        description=(
            'Agrega las líneas del extracto a la conciliación indicada en '
            '`conciliacion`; no reemplaza las que ya tiene (para volver a cargar '
            'está `limpiar`). La fecha debe estar dentro del rango de la '
            'conciliación y el valor ser distinto de cero; el detalle se recorta a '
            '150 caracteres. Procesamiento todo-o-nada.'
        ),
        request={'multipart/form-data': _ImportarSoporteRequest},
    )
    @action(
        detail=False, methods=['post'],
        parser_classes=[MultiPartParser],
        throttle_classes=[ImportarUsuarioTenantThrottle],
    )
    def importar(self, request):
        return super().importar(request)

    @extend_schema(
        summary='Limpiar extracto bancario',
        description=(
            'Borra todas las líneas del extracto de la conciliación, para volver a '
            'cargarlo. Si alguna está conciliada no borra ninguna: hay que '
            'desconciliarla primero.'
        ),
        request=inline_serializer(
            name='ConciliacionSoporteLimpiarRequest',
            fields={'conciliacion': serializers.IntegerField()},
        ),
        responses=inline_serializer(
            name='ConciliacionSoporteLimpiarResponse',
            fields={'eliminados': serializers.IntegerField()},
        ),
    )
    @action(detail=False, methods=['post'])
    def limpiar(self, request):
        conciliacion = self._conciliacion()
        with transaction.atomic():
            # Bloquea la conciliación: un `importar` en curso sobre ella termina
            # antes de que se borre, en vez de cruzarse.
            ConConciliacion.objects.select_for_update().get(pk=conciliacion.pk)
            soportes = ConConciliacionSoporte.objects.filter(conciliacion=conciliacion)
            conciliados = soportes.filter(estado_conciliado=True).count()
            if conciliados:
                raise ValidationError({
                    'detail': (
                        f'El extracto tiene {conciliados} '
                        f'{"línea conciliada" if conciliados == 1 else "líneas conciliadas"}. '
                        f'Desconcílielas primero.'
                    ),
                })
            eliminados, _ = soportes.delete()
        return Response({'eliminados': eliminados}, status=status.HTTP_200_OK)
