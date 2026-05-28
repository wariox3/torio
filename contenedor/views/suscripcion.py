import hashlib
from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnCliente, CtnContacto, CtnSuscripcion, CtnSuscripcionTipo
from contenedor.serializers import CtnSuscripcionSerializer

_LIST_PARAMS = [
    OpenApiParameter('cliente_id', int, description='Filtrar por cliente'),
    OpenApiParameter('usuario_id', int, description='Filtrar por usuario'),
    OpenApiParameter('suscripcion_tipo_id', int, description='Filtrar por tipo de suscripción'),
]


_PERIODOS_VALIDOS = (CtnSuscripcion.FRECUENCIA_MENSUAL, CtnSuscripcion.FRECUENCIA_ANUAL)


class _IntegridadRequestSerializer(serializers.Serializer):
    suscripcion_id = serializers.IntegerField(min_value=1)
    suscripcion_tipo_id = serializers.IntegerField(min_value=1)
    periodo = serializers.ChoiceField(choices=_PERIODOS_VALIDOS)
    contacto_id = serializers.IntegerField(min_value=1)
    cliente_id = serializers.IntegerField(min_value=1)
    monto_cents = serializers.IntegerField(min_value=1)
    moneda = serializers.CharField(max_length=3, default='COP')


class _IntegridadResponseSerializer(serializers.Serializer):
    referencia = serializers.CharField()
    hash = serializers.CharField()


class _ActualizarRequestSerializer(serializers.Serializer):
    suscripcion_id = serializers.IntegerField(min_value=1)
    suscripcion_tipo_id = serializers.IntegerField(min_value=1)
    frecuencia = serializers.ChoiceField(choices=_PERIODOS_VALIDOS)


@extend_schema(tags=['Suscripcion'])
class CtnSuscripcionViewSet(viewsets.ModelViewSet):
    serializer_class = CtnSuscripcionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnSuscripcion.objects.select_related('cliente', 'usuario', 'suscripcion_tipo').order_by('-fecha_inicio')
        cliente_id = self.request.query_params.get('cliente_id')
        usuario_id = self.request.query_params.get('usuario_id')
        suscripcion_tipo_id = self.request.query_params.get('suscripcion_tipo_id')
        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        if suscripcion_tipo_id:
            qs = qs.filter(suscripcion_tipo_id=suscripcion_tipo_id)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Suscripciones del usuario autenticado',
        description='Retorna las suscripciones creadas por el usuario autenticado.',
        responses=CtnSuscripcionSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='lista-usuario')
    def lista_usuario(self, request):
        qs = CtnSuscripcion.objects.filter(
            usuario=request.user,
        ).select_related('cliente', 'suscripcion_tipo').order_by('-fecha_inicio')
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CtnSuscripcionSerializer(pagina, many=True).data)

    @extend_schema(
        summary='Firma de integridad Wompi',
        description=(
            'Recibe los componentes de la referencia, valida que existan, arma la referencia '
            '`{suscripcion_id}-{suscripcion_tipo_id}-{periodo}-{contacto_id}-{cliente_id}-{timestamp}` '
            'y genera el hash de integridad SHA256 sobre referencia + monto_cents + moneda + WOMPI_INTEGRITY_SECRET.'
        ),
        request=_IntegridadRequestSerializer,
        responses={
            200: _IntegridadResponseSerializer,
            400: OpenApiResponse(
                inline_serializer('IntegridadErrorSerializer', {'detail': serializers.CharField()}),
                description='Payload inválido o secreto no configurado',
            ),
            404: OpenApiResponse(
                inline_serializer('IntegridadNotFoundSerializer', {'detail': serializers.CharField()}),
                description='Alguno de los recursos referenciados no existe',
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='integridad')
    def integridad(self, request):
        serializador = _IntegridadRequestSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        secreto = settings.WOMPI_INTEGRITY_SECRET
        if not secreto:
            return Response(
                {'detail': 'WOMPI_INTEGRITY_SECRET no está configurado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suscripcion_id = serializador.validated_data['suscripcion_id']
        suscripcion_tipo_id = serializador.validated_data['suscripcion_tipo_id']
        periodo = serializador.validated_data['periodo']
        contacto_id = serializador.validated_data['contacto_id']
        cliente_id = serializador.validated_data['cliente_id']
        monto_cents = serializador.validated_data['monto_cents']
        moneda = serializador.validated_data['moneda']

        suscripcion = CtnSuscripcion.objects.filter(id=suscripcion_id, usuario=request.user).first()
        if suscripcion is None:
            return Response(
                {'detail': f'Suscripción {suscripcion_id} no existe o no pertenece al usuario.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not CtnSuscripcionTipo.objects.filter(id=suscripcion_tipo_id).exists():
            return Response(
                {'detail': f'Tipo de suscripción {suscripcion_tipo_id} no existe.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not CtnContacto.objects.filter(id=contacto_id, usuario=request.user).exists():
            return Response(
                {'detail': f'Contacto {contacto_id} no existe o no pertenece al usuario.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not CtnCliente.objects.filter(id=cliente_id).exists():
            return Response(
                {'detail': f'Cliente {cliente_id} no existe.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        referencia = f'{suscripcion_id}-{suscripcion_tipo_id}-{periodo}-{contacto_id}-{cliente_id}-{timestamp}'
        suscripcion.referencia_pago = referencia
        suscripcion.save(update_fields=['referencia_pago'])

        cadena = f'{referencia}{monto_cents}{moneda}{secreto}'
        hash_integridad = hashlib.sha256(cadena.encode('utf-8')).hexdigest()
        return Response(
            {'referencia': referencia, 'hash': hash_integridad},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary='Actualizar suscripción (tipo y frecuencia)',
        description='Actualiza el `suscripcion_tipo` y la `frecuencia` de una suscripción del usuario autenticado. El `precio` se recalcula automáticamente en el save() del modelo.',
        request=_ActualizarRequestSerializer,
        responses={
            200: CtnSuscripcionSerializer,
            404: OpenApiResponse(
                inline_serializer('ActualizarNotFoundSerializer', {'detail': serializers.CharField()}),
                description='Suscripción o tipo no encontrado',
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='actualizar')
    def actualizar(self, request):
        # Importante: falta validacion para que por front no me vayan a vulnerar el precio. 
        # El precio se debe recalcular en el save() del modelo, no debe venir del front.
        # Por ejemplo que no tengan saldo a favor y en la actualizacion me pongan un plan mayor
        # sin pagar la diferencia. 
        # Esto se puede manejar con una validacion custom en el serializer o directamente en la vista, pero no debe venir del front.
        serializador = _ActualizarRequestSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        suscripcion_id = serializador.validated_data['suscripcion_id']
        suscripcion_tipo_id = serializador.validated_data['suscripcion_tipo_id']
        frecuencia = serializador.validated_data['frecuencia']

        suscripcion = CtnSuscripcion.objects.filter(id=suscripcion_id, usuario=request.user).first()
        if suscripcion is None:
            return Response(
                {'detail': f'Suscripción {suscripcion_id} no existe o no pertenece al usuario.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not CtnSuscripcionTipo.objects.filter(id=suscripcion_tipo_id).exists():
            return Response(
                {'detail': f'Tipo de suscripción {suscripcion_tipo_id} no existe.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        fecha_inicio = date.today()
        if frecuencia == CtnSuscripcion.FRECUENCIA_ANUAL:
            fecha_fin = fecha_inicio + relativedelta(years=1)
        else:
            fecha_fin = fecha_inicio + relativedelta(months=1)

        suscripcion.suscripcion_tipo_id = suscripcion_tipo_id
        suscripcion.frecuencia = frecuencia
        suscripcion.fecha_inicio = fecha_inicio
        suscripcion.fecha_fin = fecha_fin
        suscripcion.save(update_fields=['suscripcion_tipo', 'frecuencia', 'fecha_inicio', 'fecha_fin'])

        return Response(CtnSuscripcionSerializer(suscripcion).data, status=status.HTTP_200_OK)
