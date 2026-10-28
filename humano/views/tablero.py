"""
Datos de las tarjetas y gráficos del inicio de humano: un endpoint por indicador,
bajo `/humano/tablero/<indicador>/`, con la lógica en `humano/servicios/`.

Es el tablero de inicio: lo ve cualquier miembro con suscripción, sin el permiso
de modelo.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from humano.servicios import contrato as contrato_servicio
from seguridad.permissions import EsMiembroDelTenant, SuscripcionVigente


# De solo documentación: la vista responde el dict del servicio tal cual.
class ContratoRespuestaSerializer(serializers.Serializer):
    fecha = serializers.DateField(help_text='Hoy: el mes de `ingresos_mes` y `retiros_mes`.')
    contratos = serializers.IntegerField()
    contratos_activos = serializers.IntegerField()
    contratos_terminados = serializers.IntegerField()
    ingresos_mes = serializers.IntegerField()
    retiros_mes = serializers.IntegerField()


@extend_schema(tags=['Tablero'])
class HumTableroViewSet(viewsets.ViewSet):
    permission_classes = [EsMiembroDelTenant, SuscripcionVigente]

    @extend_schema(
        summary='Resumen de los contratos',
        description=(
            'Cantidades del tablero de inicio de humano:\n\n'
            '- `contratos`: todos los contratos.\n'
            '- `contratos_activos`: los que no están terminados.\n'
            '- `contratos_terminados`: los terminados.\n'
            '- `ingresos_mes`: contratos que empiezan en el mes de `fecha` (hoy).\n'
            '- `retiros_mes`: contratos terminados cuya `fecha_hasta` cae en ese mes.\n\n'
            'Activos y terminados suman `contratos`.'
        ),
        responses=ContratoRespuestaSerializer,
    )
    @action(detail=False, methods=['get'], url_path='contrato')
    def contrato(self, request):
        return Response(contrato_servicio.resumen(), status=status.HTTP_200_OK)
