import re

from django_tenants.utils import schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response

from contenedor.models import CtnCliente
from general.servicios import factura_electronica, rededoc


class FirmaInvalida(APIException):
    """
    401 fijo. `AuthenticationFailed` no sirve: en una vista sin clases de
    autenticación DRF no tiene header `WWW-Authenticate` que mandar y lo convierte
    en 403.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Firma inválida.'
    default_code = 'firma_invalida'


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
    # El alcance del `ScopedRateThrottle` del webhook. Va en la clase y no en el
    # `@action`: el router pasa los kwargs de la acción a `as_view`, que solo
    # acepta atributos que la clase ya declare.
    throttle_scope = 'rededoc_webhook'

    @extend_schema(
        summary='Webhook RedEDoc',
        description=(
            'Recibe los avisos de RedEDoc sobre un documento electrónico: '
            '`validacion` (la DIAN lo aceptó; trae `fecha_validacion` y `cufe`) y '
            '`notificacion` (se le entregó al adquiriente).\n\n'
            'Cada aviso viene firmado: `X-Rededoc-Fecha` (timestamp unix) y '
            '`X-Rededoc-Firma: v1=<hex>`, el HMAC-SHA256 de `<fecha>.<cuerpo crudo>` '
            'con el secreto compartido. Una firma que no cuadra, o una fecha de '
            'más de 5 minutos, responde 401 sin mirar el cuerpo.\n\n'
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
        # Límite propio y no el `anon` general: corre antes que la firma, por IP, y
        # todos los avisos legítimos vienen de la misma, la de rededoc. Lo cuenta
        # cada worker de gunicorn por separado; la protección seria contra una
        # inundación va en Nginx (`limit_req`), que cuenta en todo el servidor.
        throttle_classes=[ScopedRateThrottle],
        url_path='webhook',
    )
    def webhook(self, request):
        # Antes de tocar `request.data`: la firma es sobre el cuerpo crudo, y una
        # vez que DRF lo parsea ya no se puede releer.
        if not rededoc.firma_valida(
            request.body,
            request.headers.get(rededoc.HEADER_FECHA, ''),
            request.headers.get(rededoc.HEADER_FIRMA, ''),
        ):
            raise FirmaInvalida()

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
