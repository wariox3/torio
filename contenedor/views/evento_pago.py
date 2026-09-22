import hashlib
import hmac
import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnEventoPago, CtnMovimiento, CtnSuscripcion
from contenedor.serializers import CtnEventoPagoSerializer

logger = logging.getLogger(__name__)


class FirmaWompiInvalida(APIException):
    """
    401 fijo, igual que el webhook de rededoc: `AuthenticationFailed` en una vista
    sin clases de autenticación sale como 403.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Firma inválida.'
    default_code = 'firma_invalida'


def _valor(datos, ruta):
    """El valor de `ruta` («transaction.id») dentro de `datos`, o cadena vacía."""
    valor = datos
    for parte in ruta.split('.'):
        if not isinstance(valor, dict):
            return ''
        valor = valor.get(parte)
    return '' if valor is None else str(valor)


def firma_wompi_valida(evento):
    """
    ¿El evento lo firmó Wompi con nuestro secreto de eventos?

    Es el algoritmo de la documentación de eventos de Wompi: se concatenan los
    valores de los campos que lista `signature.properties` —rutas dentro de
    `data`, como `transaction.id`—, en ese orden; luego el `timestamp` del evento
    y al final `WOMPI_EVENTS_SECRET`. El SHA-256 de eso, en hex, es
    `signature.checksum`.

    Sin secreto configurado se rechaza todo: aceptar eventos sin verificar deja que
    cualquiera extienda una suscripción mandando un «APPROVED» inventado.
    """
    secreto = settings.WOMPI_EVENTS_SECRET
    if not secreto:
        logger.error('Evento de Wompi rechazado: WOMPI_EVENTS_SECRET no está configurado')
        return False

    firma = evento.get('signature')
    if not isinstance(firma, dict):
        return False
    propiedades = firma.get('properties')
    checksum = firma.get('checksum')
    timestamp = evento.get('timestamp')
    if not isinstance(propiedades, list) or not propiedades or not checksum or timestamp is None:
        return False

    datos = evento.get('data') or {}
    cadena = ''.join(_valor(datos, propiedad) for propiedad in propiedades)
    esperado = hashlib.sha256(f'{cadena}{timestamp}{secreto}'.encode()).hexdigest()
    # Wompi lo manda en mayúsculas; el hex es el mismo.
    return hmac.compare_digest(esperado, str(checksum).lower())


@extend_schema(tags=['Evento pago'])
class CtnEventoPagoViewSet(viewsets.GenericViewSet):
    serializer_class = CtnEventoPagoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CtnEventoPago.objects.all()

    @extend_schema(
        summary='Webhook Wompi',
        description=(
            'Recibe notificaciones de eventos de pago desde Wompi y registra el evento.\n\n'
            'Solo acepta eventos firmados por Wompi (`signature.checksum`, con '
            '`WOMPI_EVENTS_SECRET`): uno sin firma válida responde 401 y no se registra. '
            'Una transacción aprobada que ya se aplicó no se vuelve a aplicar.'
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                inline_serializer('WebhookOkSerializer', {'detalle': serializers.CharField()}),
                description='Evento registrado correctamente',
            ),
            400: OpenApiResponse(
                inline_serializer('WebhookErrorSerializer', {'detail': serializers.CharField()}),
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
                {'detail': 'Payload inválido'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Antes de registrar nada: un evento sin firma válida no deja rastro en
        # `CtnEventoPago` ni toca la suscripción.
        if not firma_wompi_valida(payload):
            raise FirmaWompiInvalida()

        transaccion = (payload.get('data') or {}).get('transaction') or {}

        # Wompi reintenta el mismo evento si no recibe 200, y un evento legítimo
        # capturado sigue teniendo la firma válida: sin esto, reenviarlo extendía la
        # suscripción otra vez. Una transacción aprobada se aplica una sola vez.
        if transaccion.get('status') == 'APPROVED' and CtnEventoPago.objects.filter(
            transaccion=transaccion.get('id'), estado='APPROVED',
        ).exists():
            logger.info('Webhook Wompi: transacción %s ya aplicada', transaccion.get('id'))
            return Response({'detalle': 'OK'}, status=status.HTTP_200_OK)
        monto_centavos = transaccion.get('amount_in_cents') or 0

        partes = (transaccion.get('reference') or '').split('-')
        suscripcion_id = partes[0] if len(partes) > 0 else None
        suscripcion_tipo_id = partes[1] if len(partes) > 1 else None
        periodo = partes[2] if len(partes) > 2 else None
        contacto_id = partes[3] if len(partes) > 3 else None
        cliente_id = partes[4] if len(partes) > 4 else None

        try:
            self._aplicar(payload, transaccion, monto_centavos, suscripcion_id,
                          suscripcion_tipo_id, periodo, contacto_id, cliente_id)
        except IntegrityError:
            # Otra entrega del mismo evento aprobado llegó a la vez y se aplicó
            # primero: la restricción única lo frenó y la transacción entera se
            # deshizo. Para Wompi es un evento recibido.
            logger.info('Webhook Wompi: transacción %s ya aplicada (concurrente)', transaccion.get('id'))

        return Response({'detalle': 'OK'}, status=status.HTTP_200_OK)

    @staticmethod
    def _aplicar(payload, transaccion, monto_centavos, suscripcion_id,
                 suscripcion_tipo_id, periodo, contacto_id, cliente_id):
        """Registra el evento y, si está aprobado, aplica el pago. Todo o nada."""
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
