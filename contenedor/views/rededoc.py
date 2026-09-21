import re

from django_tenants.utils import schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from contenedor.models import CtnCliente
from general.servicios import factura_electronica


class FechaHoraField(serializers.DateTimeField):
    """
    Fecha y hora, sin aceptar la fecha sola.

    Desde Python 3.11 `datetime.fromisoformat` acepta `2026-09-21` y lo toma como
    medianoche, así que el `DateTimeField` de DRF dejaba pasar una fecha sin hora
    y la validación quedaba registrada a las 00:00.
    """

    default_error_messages = {
        'sin_hora': 'Tiene que traer fecha y hora, por ejemplo 2026-09-21T10:15:00-05:00.',
    }

    def to_internal_value(self, value):
        if isinstance(value, str) and re.fullmatch(r'\s*\d{4}-\d{2}-\d{2}\s*', value):
            self.fail('sin_hora')
        return super().to_internal_value(value)


class RededocAvisoSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=factura_electronica.AVISOS)
    cliente = serializers.IntegerField(min_value=1, help_text='Id del cliente (tenant) en torio.')
    documento = serializers.UUIDField(help_text='Id del documento en rededoc.')
    fecha_validacion = FechaHoraField(required=False, allow_null=True)
    cufe = serializers.CharField(max_length=150, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        # Una validación sin CUFE ni fecha dejaría el documento marcado como
        # validado sin lo que lo prueba.
        if attrs['tipo'] == factura_electronica.AVISO_VALIDACION:
            faltan = {
                campo: 'Es obligatorio en un aviso de validación.'
                for campo in ('fecha_validacion', 'cufe')
                if not attrs.get(campo)
            }
            if faltan:
                raise serializers.ValidationError(faltan)
        return attrs


@extend_schema(tags=['Rededoc'])
class CtnRededocViewSet(viewsets.GenericViewSet):

    @extend_schema(
        summary='Webhook RedEDoc',
        description=(
            'Recibe los avisos de RedEDoc sobre un documento electrónico: '
            '`validacion` (la DIAN lo aceptó; trae `fecha_validacion` y `cufe`) y '
            '`notificacion` (se le entregó al adquiriente).\n\n'
            'Un cliente o un documento que no existen responden el mismo 404, '
            'para no revelar qué clientes hay.'
        ),
        request=RededocAvisoSerializer,
        responses={200: None},
    )
    @action(
        detail=False,
        methods=['post'],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path='webhook',
    )
    def webhook(self, request):
        serializer = RededocAvisoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        cliente = CtnCliente.objects.filter(pk=datos['cliente']).first()
        if cliente is None:
            raise NotFound('El documento no existe.')

        with schema_context(cliente.schema_name):
            factura_electronica.procesar_aviso(
                datos['tipo'], datos['documento'],
                fecha_validacion=datos.get('fecha_validacion'), cufe=datos.get('cufe'),
            )
        return Response(status=status.HTTP_200_OK)
