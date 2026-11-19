from decimal import Decimal, InvalidOperation

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from humano.models import HumContrato, HumMotivoTerminacion
from humano.serializers import (
    HumContratoExportarSerializer,
    HumContratoImportarSerializer,
    HumContratoSeleccionarSerializer,
    HumContratoSerializer,
    HumLiquidacionSerializer,
)
from humano.servicios import LiquidacionError, periodo_sugerido, terminar_contrato
from humano.servicios.vacacion import DIAS_VACACION_ANIO
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado o identificación'),
    OpenApiParameter('estado_terminado', bool, description='Filtrar por terminado'),
    OpenApiParameter('empleado', bool, description='Filtrar por contacto empleado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado o identificación'),
    OpenApiParameter('estado_terminado', bool, description='Filtrar por terminado'),
    OpenApiParameter('habilitado_turno', bool, description='Filtrar por habilitado para turnos'),
    OpenApiParameter('empleado', bool, description='Filtrar por contacto empleado'),
]


class TerminarContratoRequestSerializer(serializers.Serializer):
    contrato_id = serializers.IntegerField()
    fecha_terminacion = serializers.DateField()
    motivo_terminacion_id = serializers.IntegerField()


@extend_schema(tags=['Contrato'])
class HumContratoViewSet(
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
    serializer_class = HumContratoSerializer
    serializer_class_exportar = HumContratoExportarSerializer
    serializer_class_importar = HumContratoImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = HumContrato.objects.select_related(
            *HumContratoSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(contacto__nombre_corto__icontains=search)
                | qs.filter(contacto__numero_identificacion__icontains=search)
            )

        valor = self.request.query_params.get('estado_terminado')
        if valor is not None:
            qs = qs.filter(estado_terminado=valor.lower() == 'true')

        valor = self.request.query_params.get('empleado')
        if valor is not None:
            qs = qs.filter(contacto__empleado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumContratoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumContrato.objects.select_related('contacto').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(contacto__nombre_corto__icontains=search)
                | qs.filter(contacto__numero_identificacion__icontains=search)
            )

        valor = request.query_params.get('estado_terminado')
        if valor is not None:
            qs = qs.filter(estado_terminado=valor.lower() == 'true')

        valor = request.query_params.get('habilitado_turno')
        if valor is not None:
            qs = qs.filter(habilitado_turno=valor.lower() == 'true')

        valor = request.query_params.get('empleado')
        if valor is not None:
            qs = qs.filter(contacto__empleado=valor.lower() == 'true')

        pagina = self.paginate_queryset(qs)
        serializer = HumContratoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=TerminarContratoRequestSerializer, responses=HumLiquidacionSerializer)
    @action(detail=False, methods=['post'], url_path='terminar')
    def terminar(self, request):
        """Termina el contrato y crea su liquidación ya calculada, que es lo que responde."""
        serializer = TerminarContratoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        try:
            contrato = HumContrato.objects.get(pk=datos['contrato_id'])
        except HumContrato.DoesNotExist:
            raise NotFound('Contrato no encontrado.')
        try:
            motivo_terminacion = HumMotivoTerminacion.objects.get(pk=datos['motivo_terminacion_id'])
        except HumMotivoTerminacion.DoesNotExist:
            return Response({'detail': 'El motivo de terminación no existe.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            liquidacion = terminar_contrato(contrato, datos['fecha_terminacion'], motivo_terminacion)
        except LiquidacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumLiquidacionSerializer(liquidacion).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Periodo de vacaciones sugerido',
        description=(
            'El periodo que cubrirían `dias` días de vacaciones (hábiles disfrutados '
            'más en dinero; 15 si no se envía) a partir del último periodo cubierto '
            'del contrato. Cada día de vacaciones cubre 24 días del periodo (15 por '
            'cada 360), así que tomar menos de 15 cierra el periodo en proporción. El '
            'último periodo cubierto se calcula desde `fecha_ultimo_pago_vacacion` '
            'del contrato sumando los días de sus novedades de vacaciones '
            '(`dias_disfrutados` + `dias_dinero`).\n\n'
            '`dias_causados` son los días de vacaciones ganados desde el inicio del '
            'periodo hasta hoy (o hasta el fin del contrato, si terminó) y aún no tomados.'
        ),
        parameters=[
            OpenApiParameter('contrato_id', int, required=True),
            OpenApiParameter('dias', float, required=False, description='Días a tomar; 15 por defecto.'),
        ],
        responses=inline_serializer('PeriodoVacacion', {
            'fecha_desde_periodo': serializers.DateField(),
            'fecha_hasta_periodo': serializers.DateField(),
            'dias_causados': serializers.DecimalField(max_digits=10, decimal_places=3),
        }),
    )
    @action(detail=False, methods=['get'], url_path='periodo-vacacion')
    def periodo_vacacion(self, request):
        contrato_id = request.query_params.get('contrato_id', '')
        if not contrato_id.isdigit():
            return Response({'detail': 'contrato_id es requerido y debe ser un número.'},
                            status=status.HTTP_400_BAD_REQUEST)
        dias = request.query_params.get('dias')
        if dias is None:
            dias = DIAS_VACACION_ANIO
        else:
            try:
                dias = Decimal(dias)
            except InvalidOperation:
                return Response({'detail': 'dias debe ser un número.'}, status=status.HTTP_400_BAD_REQUEST)
            if not dias.is_finite() or dias <= 0:
                return Response({'detail': 'dias debe ser mayor que cero.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            contrato = HumContrato.objects.get(pk=contrato_id)
        except HumContrato.DoesNotExist:
            raise NotFound('Contrato no encontrado.')

        return Response(periodo_sugerido(contrato, dias), status=status.HTTP_200_OK)
