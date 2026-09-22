"""
Tareas de Celery de `general`.

Corren en el worker, fuera de cualquier request: no hay tenant resuelto, así que
cada tarea recibe el `schema_name` y entra con `schema_context`.
"""
import logging

from celery import shared_task
from django.db import connection, transaction
from django_tenants.utils import schema_context
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)

# Espera entre reintentos cuando rededoc o la pasarela de correo no responden:
# 1, 2, 4, 8, 16 y 32 minutos, algo más de una hora en total.
ESPERA_BASE_REINTENTO = 60
MAXIMO_REINTENTOS = 6


def programar_notificacion(documento_id):
    """
    Encola la notificación del documento cuando la transacción en curso se confirme.

    `on_commit` y no `delay` directo: el worker podría tomar la tarea antes de que
    se guardara la validación, leer el documento sin validar y descartarlo.

    Una falla al encolar —RabbitMQ caído— se registra y no sube: quien llama es el
    webhook de rededoc, que tiene que responder 200 porque la validación ya quedó
    guardada. Si respondiera error, rededoc reintentaría y recibiría 409 («ya estaba
    validado»), y la notificación no se volvería a programar nunca.
    """
    schema_name = connection.schema_name

    def encolar():
        try:
            notificar_documento.delay(schema_name, documento_id)
        except Exception:
            logger.exception(
                'No se pudo encolar la notificación del documento %s (schema %s)',
                documento_id, schema_name,
            )

    transaction.on_commit(encolar)


@shared_task(bind=True, max_retries=MAXIMO_REINTENTOS)
def notificar_documento(self, schema_name, documento_id):
    """
    Notifica al adquiriente un documento que la DIAN acaba de validar.

    Puede correr dos veces con el mismo documento —`acks_late`, o dos avisos de
    validación seguidos— y por eso toma la fila con `skip_locked` y no hace nada si
    ya está notificado: el daño de correr de más sería un correo repetido al cliente.

    Si rededoc o su pasarela de correo no responden (5xx), se reintenta con espera
    creciente. Si rechaza el documento (4xx, por ejemplo un adquiriente sin correo),
    reintentar no lo arregla: se registra y se deja, y se puede notificar a mano
    con `documento/notificar/` después de corregir el dato.
    """
    # Los imports van acá: el worker carga las tareas al arrancar, y la
    # facturación electrónica arrastra formatos y modelos que no necesita hasta
    # que llega la primera tarea.
    from general.models import GenDocumento
    from general.servicios import factura_electronica

    with schema_context(schema_name):
        with transaction.atomic():
            documento = (
                GenDocumento.objects.select_for_update(skip_locked=True, of=('self',))
                .select_related('contacto')
                .filter(pk=documento_id).first()
            )
            if documento is None:
                # O no existe, o la tiene otro worker en este momento.
                return
            if documento.estado_electronico_notificado:
                return
            # Sin correo de facturación electrónica no se notifica, y no es un
            # error: queda pendiente y la pantalla de pendientes lo muestra.
            if not factura_electronica.tiene_correo_facturacion(documento):
                logger.info(
                    'Documento %s (schema %s) sin correo de facturación electrónica: '
                    'no se notifica', documento_id, schema_name,
                )
                return
            try:
                factura_electronica.notificar([documento_id])
            except factura_electronica.ErrorFacturaElectronica as error:
                if error.status >= 500:
                    raise self.retry(
                        exc=error, countdown=ESPERA_BASE_REINTENTO * 2 ** self.request.retries,
                    )
                logger.warning(
                    'Rededoc rechazó la notificación del documento %s (schema %s): %s',
                    documento_id, schema_name, error.cuerpo,
                )
            except APIException as error:
                # Una validación de torio: el documento dejó de cumplir algo entre
                # que se encoló y que se corrió. Reintentar no lo arregla.
                logger.warning(
                    'La notificación del documento %s (schema %s) no procede: %s',
                    documento_id, schema_name, error.detail,
                )
