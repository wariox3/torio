"""
Tareas de Celery de `humano`.

Corren en el worker, fuera de cualquier request: no hay tenant resuelto, así que
cada tarea recibe el `schema_name` y entra con `schema_context`.
"""
import base64
import logging

from celery import shared_task
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.html import escape
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

# Espera entre reintentos cuando la pasarela de correo no responde: 1, 2, 4, 8, 16
# y 32 minutos, igual que la notificación de documentos de `general`.
ESPERA_BASE_REINTENTO = 60
MAXIMO_REINTENTOS = 6

ASUNTO_NOMINA = 'Notificación de nómina'


def correo_nomina(documento):
    """
    El correo del empleado al que se le envía su nómina, o `None` si no tiene uno
    válido. Se mira al encolar —para decirle al usuario a quién no le llega— y otra
    vez al enviar, porque entre una cosa y la otra el correo pudo cambiar.
    """
    contacto = documento.contacto
    correo = ((contacto.correo if contacto is not None else None) or '').strip()
    if not correo:
        return None
    try:
        validate_email(correo)
    except ValidationError:
        return None
    return correo


@shared_task(bind=True, max_retries=MAXIMO_REINTENTOS)
def notificar_nomina(self, schema_name, documento_id):
    """
    Le envía a un empleado el desprendible de su nómina, en PDF adjunto.

    Una tarea por empleado: si la pasarela falla con uno, se reintenta ese y no se
    les vuelve a escribir a los que ya lo recibieron.

    Correr dos veces —`acks_late` tras una caída del worker— le manda el correo
    repetido a ese empleado. Se acepta: notificar una programación se puede repetir
    a mano cuantas veces se quiera, así que un correo de más es lo mismo que el
    usuario puede hacer con un clic, y llevar una marca por documento no lo vale.

    Si la pasarela no responde (5xx) se reintenta con espera creciente; si rechaza
    el correo (4xx), reintentar no lo arregla y se registra.
    """
    # Los imports van acá: el worker carga las tareas al arrancar, y los formatos
    # arrastran modelos y reportlab que no necesita hasta la primera tarea.
    from general.models import GenDocumento
    from general.servicios import documento_imprimir
    from utilidades.zinc import Zinc

    with schema_context(schema_name):
        documento = (
            GenDocumento.objects
            .select_related('documento_tipo', 'contacto__banco', 'contrato__cargo', 'contrato__grupo')
            .filter(pk=documento_id).first()
        )
        if documento is None:
            return
        correo = correo_nomina(documento)
        if correo is None:
            logger.info(
                'Nómina %s (schema %s) sin correo válido: no se notifica', documento_id, schema_name,
            )
            return

        contenido, nombre = documento_imprimir.pdf_documento(documento)
        html = (
            f'<h2>Estimado/a {escape(documento.contacto.nombre_corto)}</h2>'
            f'<p>Le informamos que su nómina está lista y adjunta en este correo.</p>'
            f'<p>Por favor, revise el archivo adjunto.</p>'
            f'<p>Saludos cordiales,</p>'
            f'<p>El equipo de Nómina</p>'
        )
        archivos = [{'B64': base64.b64encode(contenido).decode('ascii'), 'NombreArchivo': nombre}]

    respuesta = Zinc().correo(correo, ASUNTO_NOMINA, html, archivos=archivos)
    if not respuesta['error']:
        return
    if respuesta['status'] >= 500:
        raise self.retry(countdown=ESPERA_BASE_REINTENTO * 2 ** self.request.retries)
    logger.warning(
        'Zinc rechazó la nómina %s (schema %s) para %s: %s',
        documento_id, schema_name, correo, respuesta['datos'],
    )
