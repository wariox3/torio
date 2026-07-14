import calendar
from collections import OrderedDict
from datetime import date

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumentoDetalle
from turno.models import TurProgramacionSimulacion
from turno.serializers import (
    TurProgramacionSimulacionExportarSerializer,
    TurProgramacionSimulacionImportarSerializer,
    TurProgramacionSimulacionSerializer,
)
from turno.servicios import simular as simular_servicio
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin


class SimularRequestSerializer(serializers.Serializer):
    documento_detalle_id = serializers.IntegerField()
    anio = serializers.IntegerField(min_value=2000, max_value=2100)
    mes = serializers.IntegerField(min_value=1, max_value=12)


_LIST_PARAMS = [
    OpenApiParameter('fecha', str, description='Filtrar por fecha (AAAA-MM-DD)'),
    OpenApiParameter('turno', int, description='Filtrar por turno'),
    OpenApiParameter('documento_detalle', int, description='Filtrar por documento detalle'),
]


@extend_schema(tags=['Turno'])
class TurProgramacionSimulacionViewSet(
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
    serializer_class = TurProgramacionSimulacionSerializer
    serializer_class_exportar = TurProgramacionSimulacionExportarSerializer
    serializer_class_importar = TurProgramacionSimulacionImportarSerializer

    def get_queryset(self):
        qs = TurProgramacionSimulacion.objects.select_related(
            *TurProgramacionSimulacionSerializer.select_related_lista
        ).order_by('fecha', 'id')

        fecha = self.request.query_params.get('fecha')
        if fecha:
            qs = qs.filter(fecha=fecha)

        turno = self.request.query_params.get('turno')
        if turno:
            qs = qs.filter(turno_id=turno)

        documento_detalle = self.request.query_params.get('documento_detalle')
        if documento_detalle:
            qs = qs.filter(documento_detalle_id=documento_detalle)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=SimularRequestSerializer)
    @action(detail=False, methods=['post'], url_path='simular')
    def simular(self, request):
        serializer = SimularRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        if not GenDocumentoDetalle.objects.filter(pk=datos['documento_detalle_id']).exists():
            raise NotFound('Documento detalle no encontrado.')

        creados = simular_servicio(
            datos['documento_detalle_id'], datos['anio'], datos['mes'],
        )
        return Response({'creados': creados}, status=status.HTTP_200_OK)

    @extend_schema(request=None)
    @action(detail=False, methods=['post'], url_path='limpiar')
    def limpiar(self, request):
        """Vacía el buffer de simulación (es de una sola corrida: se borra completo)."""
        eliminados, _ = TurProgramacionSimulacion.objects.all().delete()
        return Response({'eliminados': eliminados}, status=status.HTTP_200_OK)

    @extend_schema(parameters=[
        OpenApiParameter(
            'documento_detalle', int, required=True, description='Documento detalle simulado',
        ),
        OpenApiParameter('anio', int, required=True, description='Año de la grilla'),
        OpenApiParameter('mes', int, required=True, description='Mes de la grilla (1-12)'),
    ])
    @action(detail=False, methods=['get'], url_path='detalle')
    def detalle(self, request):
        # Grilla horizontal del documento_detalle pedido: una fila por contrato simulado,
        # columnas = los días del mes pedido.
        valor = request.query_params.get('documento_detalle')
        if not valor:
            raise ValidationError({'detail': 'El parámetro documento_detalle es obligatorio.'})
        try:
            documento_detalle_id = int(valor)
        except (TypeError, ValueError):
            raise ValidationError(
                {'detail': 'El parámetro documento_detalle debe ser un entero.'}
            )

        valor = request.query_params.get('anio')
        if not valor:
            raise ValidationError({'detail': 'El parámetro anio es obligatorio.'})
        try:
            anio = int(valor)
        except (TypeError, ValueError):
            raise ValidationError({'detail': 'El parámetro anio debe ser un entero.'})
        if anio < 2000 or anio > 2100:
            raise ValidationError({'detail': 'El parámetro anio debe estar entre 2000 y 2100.'})

        valor = request.query_params.get('mes')
        if not valor:
            raise ValidationError({'detail': 'El parámetro mes es obligatorio.'})
        try:
            mes = int(valor)
        except (TypeError, ValueError):
            raise ValidationError({'detail': 'El parámetro mes debe ser un entero.'})
        if mes < 1 or mes > 12:
            raise ValidationError({'detail': 'El parámetro mes debe estar entre 1 y 12.'})

        detalle = GenDocumentoDetalle.objects.filter(pk=documento_detalle_id).first()
        if detalle is None:
            raise NotFound('Documento detalle no encontrado.')

        # Columnas: los días del mes pedido.
        dias_mes = calendar.monthrange(anio, mes)[1]
        fechas_iso = [
            date(anio, mes, dia).isoformat() for dia in range(1, dias_mes + 1)
        ]

        simulaciones = (
            TurProgramacionSimulacion.objects
            .filter(
                documento_detalle_id=documento_detalle_id,
                fecha__year=anio,
                fecha__month=mes,
            )
            .select_related('contrato__contacto', 'turno')
            .order_by('fecha', 'id')
        )

        # Agrupar por contrato -> {fecha_iso: simulacion}: una fila por contrato.
        grupos = OrderedDict()
        for s in simulaciones:
            grupos.setdefault(s.contrato_id, {})[s.fecha.isoformat()] = s

        def celda(s):
            if s is None:
                return None
            return {
                'simulacion_id': s.id,
                'turno_id': s.turno_id,
                'turno_codigo': s.turno.codigo if s.turno else None,
                'turno_nombre': s.turno.nombre if s.turno else None,
                'horas': s.horas,
                'horas_diurnas': s.horas_diurnas,
                'horas_nocturnas': s.horas_nocturnas,
                'festivo': s.festivo,
            }

        def construir_fila(contrato, por_fecha):
            contacto = contrato.contacto if contrato else None
            return {
                'documento_detalle_id': detalle.id,
                'contrato_id': contrato.id if contrato else None,
                'contrato_contacto_id': contrato.contacto_id if contrato else None,
                'contrato_contacto_nombre_corto': (
                    contacto.nombre_corto if contacto else None
                ),
                'contrato_contacto_numero_identificacion': (
                    contacto.numero_identificacion if contacto else None
                ),
                'dias': {iso: celda(por_fecha.get(iso)) for iso in fechas_iso},
            }

        filas = [
            construir_fila(next(iter(por_fecha.values())).contrato, por_fecha)
            for por_fecha in grupos.values()
        ]
        if not filas:
            filas.append(construir_fila(None, {}))

        return Response({
            'fechas': fechas_iso,
            'filas': filas,
        })
