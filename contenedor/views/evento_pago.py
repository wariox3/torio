import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnEventoPago, CtnMovimiento, CtnSuscripcion
from contenedor.serializers import CtnEventoPagoSerializer

logger = logging.getLogger(__name__)


@extend_schema(tags=['Evento pago'])
class CtnEventoPagoViewSet(viewsets.GenericViewSet):
    serializer_class = CtnEventoPagoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CtnEventoPago.objects.all()

    @extend_schema(
        summary='Webhook Wompi',
        description='Recibe notificaciones de eventos de pago desde Wompi y registra el evento.',
        request=None,
        responses={
            200: OpenApiResponse(
                inline_serializer('WebhookOkSerializer', {'detalle': serializers.CharField()}),
                description='Evento registrado correctamente',
            ),
            400: OpenApiResponse(
                inline_serializer('WebhookErrorSerializer', {'detalle': serializers.CharField()}),
                description='Payload inválido',
            ),
        },
    )
    @action(
        detail=False,
        methods=['post'],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path='webhook-wompi',
    )
    def webhook_wompi(self, request):
        payload = request.data
        if not isinstance(payload, dict):
            return Response(
                {'detalle': 'Payload inválido'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transaccion = (payload.get('data') or {}).get('transaction') or {}
        monto_centavos = transaccion.get('amount_in_cents') or 0

        partes = (transaccion.get('reference') or '').split('-')
        suscripcion_id = partes[0] if len(partes) > 0 else None
        suscripcion_tipo_id = partes[1] if len(partes) > 1 else None
        periodo = partes[2] if len(partes) > 2 else None
        contacto_id = partes[3] if len(partes) > 3 else None
        cliente_id = partes[4] if len(partes) > 4 else None

        with transaction.atomic():
            evento_pago = CtnEventoPago.objects.create(
                evento=payload.get('event'),
                entorno=payload.get('environment'),
                transaccion=transaccion.get('id'),
                metodo_pago=transaccion.get('payment_method_type'),
                referencia=transaccion.get('reference'),
                correo=transaccion.get('customer_email'),
                estado=transaccion.get('status'),
                fecha_transaccion=transaccion.get('finalized_at') or transaccion.get('created_at'),
                vr_original=monto_centavos / 100 if monto_centavos else 0,
                datos=payload,
            )

            if transaccion.get('status') == 'APPROVED':
                try:
                    suscripcion = CtnSuscripcion.objects.select_related(
                        'usuario', 'suscripcion_tipo'
                    ).select_for_update(of=('self',)).get(id=int(suscripcion_id))
                except (CtnSuscripcion.DoesNotExist, ValueError, TypeError):
                    logger.warning('Webhook Wompi: suscripcion_id=%s no encontrada', suscripcion_id)
                else:
                    fecha_inicio = date.today()
                    if periodo == CtnSuscripcion.FRECUENCIA_ANUAL:
                        fecha_fin = fecha_inicio + relativedelta(years=1)
                    else:
                        fecha_fin = fecha_inicio + relativedelta(months=1)

                    CtnMovimiento.objects.create(
                        evento_pago=evento_pago,
                        tipo='factura',
                        concepto=f'{suscripcion.suscripcion_tipo.nombre}',
                        valor=monto_centavos / 100,
                        usuario=suscripcion.usuario,
                        contacto_id=int(contacto_id),
                        cliente_id=int(cliente_id) if cliente_id else None,
                    )

                    suscripcion.suscripcion_tipo_id = int(suscripcion_tipo_id)
                    suscripcion.frecuencia = periodo
                    suscripcion.fecha_inicio = fecha_inicio
                    suscripcion.fecha_fin = fecha_fin
                    suscripcion.save(update_fields=['suscripcion_tipo', 'frecuencia', 'fecha_inicio', 'fecha_fin'])

        return Response({'detalle': 'OK'}, status=status.HTTP_200_OK)
