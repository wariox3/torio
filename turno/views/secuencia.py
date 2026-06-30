from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from turno.models import TurSecuencia
from turno.serializers import (
    TurSecuenciaExportarSerializer,
    TurSecuenciaImportarSerializer,
    TurSecuenciaSeleccionarSerializer,
    TurSecuenciaSerializer,
)
from turno.servicios import calcular_mes
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
    OpenApiParameter('estado_inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


class CalcularMesRequestSerializer(serializers.Serializer):
    secuencia_id = serializers.IntegerField()
    posicion_inicial = serializers.IntegerField(min_value=1)
    anio = serializers.IntegerField(min_value=2000, max_value=2100)
    mes = serializers.IntegerField(min_value=1, max_value=12)


@extend_schema(tags=['Turno'])
class TurSecuenciaViewSet(
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
    serializer_class = TurSecuenciaSerializer
    serializer_class_exportar = TurSecuenciaExportarSerializer
    serializer_class_importar = TurSecuenciaImportarSerializer

    def get_queryset(self):
        qs = TurSecuencia.objects.order_by('nombre')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)

        valor = self.request.query_params.get('estado_inactivo')
        if valor is not None:
            qs = qs.filter(estado_inactivo=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=TurSecuenciaSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = TurSecuencia.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = TurSecuenciaSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=CalcularMesRequestSerializer)
    @action(detail=False, methods=['post'], url_path='calcular-mes')
    def calcular_mes(self, request):
        """
        Aplica la secuencia como patrón cíclico sobre un mes (vista previa, no persiste).

        El patrón son los primeros `secuencia.dias` slots (`dia_1`..`dia_{dias}`);
        `posicion_inicial` (1-based) indica qué slot cae en el día 1 del mes y el
        patrón se repite cada `secuencia.dias` días a lo largo del mes.
        """
        serializer = CalcularMesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        try:
            secuencia = TurSecuencia.objects.get(pk=datos['secuencia_id'])
        except TurSecuencia.DoesNotExist:
            raise NotFound('Secuencia no encontrada.')

        n = secuencia.dias
        if n <= 0:
            raise ValidationError({'secuencia_id': 'La secuencia no tiene definido el número de días del ciclo.'})
        if datos['posicion_inicial'] > n:
            raise ValidationError({'posicion_inicial': f'Debe estar entre 1 y {n} (días del ciclo).'})

        dias = calcular_mes(secuencia, datos['anio'], datos['mes'], datos['posicion_inicial'])

        return Response(
            {
                'secuencia_id': secuencia.id,
                'anio': datos['anio'],
                'mes': datos['mes'],
                'posicion_inicial': datos['posicion_inicial'],
                'ciclo_dias': n,
                'dias': dias,
            },
            status=status.HTTP_200_OK,
        )
