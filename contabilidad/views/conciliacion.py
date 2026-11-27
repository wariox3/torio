from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.models import ConConciliacion
from contabilidad.serializers import (
    ConConciliacionExportarSerializer,
    ConConciliacionImportarSerializer,
    ConConciliacionSeleccionarSerializer,
    ConConciliacionSerializer,
)
from contabilidad.servicios import conciliacion as conciliacion_servicio
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por cuenta banco'),
]


@extend_schema(tags=['Conciliación'])
class ConConciliacionViewSet(
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
    serializer_class = ConConciliacionSerializer
    serializer_class_exportar = ConConciliacionExportarSerializer
    serializer_class_importar = ConConciliacionImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        return ConConciliacion.objects.select_related(
            *ConConciliacionSerializer.select_related_lista
        ).order_by('-id')

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConConciliacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConConciliacion.objects.select_related('cuenta_banco').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(cuenta_banco__nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConConciliacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Cargar movimientos',
        description=(
            'Carga como detalles los movimientos de la cuenta contable de la cuenta '
            'bancaria: los del rango de la conciliación y los anteriores que quedaron '
            'pendientes en una conciliación previa de la misma cuenta bancaria. No '
            'carga los ya conciliados, los que ya están en esta conciliación ni los de '
            'saldo inicial o cierre, así que se puede volver a ejecutar para agregar '
            'lo nuevo. Responde 400 si la cuenta bancaria no tiene cuenta contable.'
        ),
        request=None,
        responses=inline_serializer(
            name='ConciliacionCargarResponse',
            fields={'cargados': serializers.IntegerField()},
        ),
    )
    @action(detail=True, methods=['post'])
    def cargar(self, request, pk=None):
        # `get_object` responde 404 también a un pk que no es número.
        cargados = conciliacion_servicio.cargar(self.get_object().pk)
        return Response({'cargados': cargados}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Conciliar automáticamente',
        description=(
            'Cruza 1 a 1 los detalles pendientes contra las líneas pendientes del '
            'extracto: mismo lado (débito/crédito), mismo valor exacto y fechas a no '
            'más de `dias` de diferencia (0 por defecto, máximo 31). Entre varios '
            'candidatos gana la fecha más cercana. Marca ambos lados como '
            'conciliados; no guarda qué cruzó con qué. Se puede volver a ejecutar: '
            'solo toma lo pendiente.'
        ),
        request=inline_serializer(
            name='ConciliacionConciliarRequest',
            fields={'dias': serializers.IntegerField(required=False, min_value=0, max_value=31)},
        ),
        responses=inline_serializer(
            name='ConciliacionConciliarResponse',
            fields={'conciliados': serializers.IntegerField()},
        ),
    )
    @action(detail=True, methods=['post'])
    def conciliar(self, request, pk=None):
        dias = request.data.get('dias')
        if dias in (None, ''):
            dias = 0
        else:
            if isinstance(dias, bool):
                raise ValidationError({'detail': 'dias debe ser un entero.'})
            try:
                dias = int(dias)
            except (TypeError, ValueError):
                raise ValidationError({'detail': 'dias debe ser un entero.'})
            if not 0 <= dias <= 31:
                raise ValidationError({'detail': 'dias debe estar entre 0 y 31.'})
        # `get_object` responde 404 también a un pk que no es número.
        conciliados = conciliacion_servicio.conciliar(self.get_object().pk, dias)
        return Response({'conciliados': conciliados}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Desconciliar',
        description=(
            'Devuelve a pendiente todos los detalles y todas las líneas del extracto '
            'conciliados de la conciliación. Es todo o nada: no se guarda qué cruzó '
            'con qué, así que no se puede soltar una pareja sola.'
        ),
        request=None,
        responses=inline_serializer(
            name='ConciliacionDesconciliarResponse',
            fields={
                'detalles': serializers.IntegerField(),
                'soportes': serializers.IntegerField(),
            },
        ),
    )
    @action(detail=True, methods=['post'])
    def desconciliar(self, request, pk=None):
        # `get_object` responde 404 también a un pk que no es número.
        detalles, soportes = conciliacion_servicio.desconciliar(self.get_object().pk)
        return Response({'detalles': detalles, 'soportes': soportes}, status=status.HTTP_200_OK)
