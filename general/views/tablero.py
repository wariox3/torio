"""
Datos de las tarjetas y gráficos del inicio de general: un endpoint por indicador,
bajo `/general/tablero/<indicador>/`, con la lógica en `general/servicios/`.

Es el tablero de inicio: lo ve cualquier miembro con suscripción, sin el permiso
de modelo.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from general.servicios import cartera as cartera_servicio
from general.servicios import resumen as resumen_servicio
from seguridad.permissions import EsMiembroDelTenant, SuscripcionVigente

PARAMETRO_PERIODO = OpenApiParameter(
    'periodo', OpenApiTypes.STR, required=True, enum=list(resumen_servicio.PERIODOS),
    description='Rango de `fecha` a resumir.',
)


@extend_schema(tags=['Tablero'])
class GenTableroViewSet(viewsets.ViewSet):
    permission_classes = [EsMiembroDelTenant, SuscripcionVigente]

    @extend_schema(
        summary='Resumen de la cartera',
        description=(
            'Cifras del tablero de cuentas por cobrar (`?tipo=cobrar`) o por pagar '
            '(`?tipo=pagar`), sobre los mismos documentos de los informes '
            '`cobrar_pendiente` y `pagar_pendiente`. Un documento sin `fecha_vence` '
            'vence en su `fecha`.\n\n'
            '- `total_pendiente`, `total_pendiente_vencido` (vence antes de hoy) y '
            '`total_pendiente_vigente` (vence hoy o después); los dos últimos suman '
            'el primero.'
        ),
        parameters=[
            OpenApiParameter(
                'tipo', OpenApiTypes.STR, required=True, enum=['cobrar', 'pagar'],
                description='Lado de la cartera.',
            ),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='cartera')
    def cartera(self, request):
        tipo = request.query_params.get('tipo')
        if tipo not in cartera_servicio.TIPOS:
            raise ValidationError({'detail': 'El tipo debe ser "cobrar" o "pagar".'})
        return Response(cartera_servicio.resumen(tipo), status=status.HTTP_200_OK)

    @extend_schema(
        summary='Resumen de ventas',
        description=(
            'Venta neta del periodo en curso para el tablero: documentos de venta '
            'aprobados y no anulados, por su `fecha`; la nota crédito resta.\n\n'
            '- `?periodo=mes`: el mes actual, un punto por día en `serie`.\n'
            '- `?periodo=anio`: el año actual, un punto por mes en `serie`.\n\n'
            'Los días o meses sin ventas salen en cero. `totales` suma la serie.'
        ),
        parameters=[PARAMETRO_PERIODO],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='venta')
    def venta(self, request):
        periodo = request.query_params.get('periodo')
        if periodo not in resumen_servicio.PERIODOS:
            raise ValidationError({'detail': 'El periodo debe ser "mes" o "anio".'})
        return Response(resumen_servicio.resumen('venta', periodo), status=status.HTTP_200_OK)

    @extend_schema(
        summary='Resumen de compras',
        description=(
            'Compra neta del periodo en curso para el tablero: documentos de compra '
            'aprobados y no anulados, por su `fecha`; las notas crédito y de ajuste '
            'restan.\n\n'
            '- `?periodo=mes`: el mes actual, un punto por día en `serie`.\n'
            '- `?periodo=anio`: el año actual, un punto por mes en `serie`.\n\n'
            'Los días o meses sin compras salen en cero. `totales` suma la serie.'
        ),
        parameters=[PARAMETRO_PERIODO],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='compra')
    def compra(self, request):
        periodo = request.query_params.get('periodo')
        if periodo not in resumen_servicio.PERIODOS:
            raise ValidationError({'detail': 'El periodo debe ser "mes" o "anio".'})
        return Response(resumen_servicio.resumen('compra', periodo), status=status.HTTP_200_OK)

    @extend_schema(
        summary='Resumen de ingresos contra costos y gastos',
        description=(
            'Las dos barras del tablero en cada punto del periodo en curso: `ingreso` '
            'es el subtotal neto de las ventas (los documentos de `tablero/venta`) y '
            '`egreso` el de las compras (los de `tablero/compra`) más el gasto de '
            'personal: el devengado de nómina, primas, cesantías, intereses y '
            'liquidaciones, y la parte de la empresa en la seguridad social. Va antes '
            'de impuestos: el IVA no es ingreso ni gasto.\n\n'
            '- `?periodo=mes`: el mes actual, un punto por día en `serie`.\n'
            '- `?periodo=anio`: el año actual, un punto por mes en `serie`.\n\n'
            '`totales` trae `ingreso`, `egreso` y `diferencia` (ingreso - egreso).'
        ),
        parameters=[PARAMETRO_PERIODO],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='resultado')
    def resultado(self, request):
        periodo = request.query_params.get('periodo')
        if periodo not in resumen_servicio.PERIODOS:
            raise ValidationError({'detail': 'El periodo debe ser "mes" o "anio".'})
        return Response(resumen_servicio.resultado(periodo), status=status.HTTP_200_OK)
