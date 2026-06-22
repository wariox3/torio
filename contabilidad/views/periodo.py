from itertools import groupby

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.models import ConPeriodo
from contabilidad.serializers import (
    ConPeriodoExportarSerializer,
    ConPeriodoImportarSerializer,
    ConPeriodoSeleccionarSerializer,
    ConPeriodoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

class CrearPeriodosAnioRequestSerializer(serializers.Serializer):
    anio = serializers.IntegerField(min_value=2000, max_value=2100)


_LIST_PARAMS = [
    OpenApiParameter('anio', int, description='Filtrar por año'),
    OpenApiParameter('estado_cerrado', bool, description='Filtrar por cerrado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por año'),
]


@extend_schema(tags=['Periodo'])
class ConPeriodoViewSet(
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
    serializer_class = ConPeriodoSerializer
    serializer_class_exportar = ConPeriodoExportarSerializer
    serializer_class_importar = ConPeriodoImportarSerializer

    def get_queryset(self):
        qs = ConPeriodo.objects.order_by('-anio', '-mes')

        anio = self.request.query_params.get('anio')
        if anio:
            qs = qs.filter(anio=anio)

        valor = self.request.query_params.get('estado_cerrado')
        if valor is not None:
            qs = qs.filter(estado_cerrado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConPeriodoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConPeriodo.objects.order_by('-anio', '-mes')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(anio__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConPeriodoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Periodos agrupados por año',
        description='Devuelve los periodos agrupados por año, con los años en orden descendente.',
    )
    @action(detail=False, methods=['get'])
    def anio(self, request):
        qs = ConPeriodo.objects.order_by('-anio', '-mes')
        datos = [
            {
                'anio': anio,
                'periodos': ConPeriodoSerializer(list(periodos), many=True).data,
            }
            for anio, periodos in groupby(qs, key=lambda p: p.anio)
        ]
        return Response(datos)

    @extend_schema(
        summary='Crear los periodos de un año',
        description=(
            'Genera los 13 periodos contables (meses 1–12 + cierre) para el año indicado. '
            'Falla si el año ya tiene periodos.'
        ),
        request=CrearPeriodosAnioRequestSerializer,
        responses=ConPeriodoSerializer(many=True),
    )
    @action(detail=False, methods=['post'], url_path='anio-nuevo')
    def anio_nuevo(self, request):
        serializer = CrearPeriodosAnioRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        anio = serializer.validated_data['anio']

        if ConPeriodo.objects.filter(anio=anio).exists():
            raise ValidationError({'anio': 'Ya existen periodos para este año'})

        with transaction.atomic():
            # 13 periodos: meses 1–12 + periodo 13 (ajustes/cierre).
            periodos = ConPeriodo.objects.bulk_create(
                [ConPeriodo(anio=anio, mes=mes) for mes in range(1, 14)]
            )

        datos = ConPeriodoSerializer(periodos, many=True).data
        return Response(datos, status=status.HTTP_201_CREATED)