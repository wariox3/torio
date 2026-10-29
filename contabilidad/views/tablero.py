"""
Datos de las tarjetas y gráficos del inicio de contabilidad: un endpoint por
indicador, bajo `/contabilidad/tablero/<indicador>/`, con la lógica en
`contabilidad/servicios/tablero.py`.

Es el tablero de inicio: lo ve cualquier miembro con suscripción, sin el permiso
de modelo.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.servicios import tablero as tablero_servicio
from general.views.tablero import TableroErrorRespuestaSerializer
from seguridad.permissions import EsMiembroDelTenant, SuscripcionVigente

# Serializers de solo documentación: la vista responde el dict del servicio tal cual.
# Los montos salen como número en el JSON, de ahí `coerce_to_string=False`.


def _monto(**kwargs):
    return serializers.DecimalField(max_digits=20, decimal_places=6, coerce_to_string=False, **kwargs)


class EstadoResultadosTarjetasSerializer(serializers.Serializer):
    vendimos = _monto(help_text='Ventas (grupo 41) más otros ingresos (grupo 42).')
    gastamos = _monto(help_text='Costo de ventas, gastos de operación, otros gastos (53) e impuestos.')
    nos_quedo = _monto(help_text='Utilidad neta: `vendimos − gastamos`.')
    margen_neto = serializers.DecimalField(
        max_digits=20, decimal_places=2, coerce_to_string=False, allow_null=True,
        help_text='`nos_quedo / ventas × 100`. Nulo si no hubo ventas.',
    )


class EstadoResultadosCascadaSerializer(serializers.Serializer):
    clave = serializers.ChoiceField(choices=[
        'ventas', 'costo_ventas', 'utilidad_bruta', 'gastos_operacion',
        'utilidad_operacional', 'otros_netos', 'impuestos', 'utilidad_neta',
    ])
    etiqueta = serializers.CharField()
    valor = _monto(help_text='Las salidas van negativas.')
    tipo = serializers.ChoiceField(
        choices=['entrada', 'salida', 'subtotal', 'total'],
        help_text='Las filas `entrada` y `salida` suman el `total`.',
    )


class EstadoResultadosComparativoSerializer(serializers.Serializer):
    fecha_desde = serializers.DateField()
    fecha_hasta = serializers.DateField()
    vendimos = _monto()
    gastamos = _monto()
    nos_quedo = _monto()


class EstadoResultadosRespuestaSerializer(serializers.Serializer):
    fecha_desde = serializers.DateField()
    fecha_hasta = serializers.DateField()
    tarjetas = EstadoResultadosTarjetasSerializer()
    cascada = EstadoResultadosCascadaSerializer(many=True)
    comparativo = EstadoResultadosComparativoSerializer(
        help_text='Las cifras de las tarjetas para el mismo rango del año anterior.',
    )


class EstadoResultadosRequestSerializer(serializers.Serializer):
    fecha_desde = serializers.DateField(required=False)
    fecha_hasta = serializers.DateField(required=False)


RESPUESTA_400 = OpenApiResponse(
    TableroErrorRespuestaSerializer, description='Fecha inválida o rango invertido',
)


@extend_schema(tags=['Tablero'])
class ConTableroViewSet(viewsets.ViewSet):
    permission_classes = [EsMiembroDelTenant, SuscripcionVigente]

    @extend_schema(
        summary='Estado de resultados para la gráfica de cascada',
        description=(
            'Ventas, costos, gastos e impuestos del rango sobre `con_movimiento`, sin '
            'asientos de cierre. Sin fechas, va del 1 de enero del año en curso a hoy.\n\n'
            '- `ventas`: grupo 41. `costo_ventas`: clases 6 y 7. `gastos_operacion`: '
            'grupos 51 y 52. `otros_netos`: grupo 42 menos grupo 53. `impuestos`: grupo 54.\n'
            '- `comparativo`: el mismo rango un año antes.'
        ),
        parameters=[
            OpenApiParameter('fecha_desde', OpenApiTypes.DATE, description='Por defecto, 1 de enero del año en curso.'),
            OpenApiParameter('fecha_hasta', OpenApiTypes.DATE, description='Por defecto, hoy.'),
        ],
        responses={200: EstadoResultadosRespuestaSerializer, 400: RESPUESTA_400},
    )
    @action(detail=False, methods=['get'], url_path='estado-resultados')
    def estado_resultados(self, request):
        serializer = EstadoResultadosRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        fecha_desde, fecha_hasta = tablero_servicio.rango(
            serializer.validated_data.get('fecha_desde'),
            serializer.validated_data.get('fecha_hasta'),
        )
        if fecha_desde > fecha_hasta:
            raise ValidationError({'detail': 'La fecha desde no puede ser posterior a la fecha hasta.'})
        return Response(
            tablero_servicio.estado_resultados(fecha_desde, fecha_hasta), status=status.HTTP_200_OK,
        )
