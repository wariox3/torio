"""
Pruebas del webhook de rededoc (`POST /contenedor/rededoc/webhook/`).

Vive en el schema público y entra al del tenant por el `cliente` del aviso, así
que se prueba con un tenant real: el documento se crea en su schema y la vista
tiene que encontrarlo desde afuera.
"""

import json
import time
import uuid
from datetime import date, datetime

from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import ScopedRateThrottle

from contenedor.views.rededoc import CtnRededocViewSet
from general.models import GenDocumento, GenDocumentoClase, GenDocumentoTipo
from general.servicios.rededoc import firmar_aviso

SECRETO = 'secreto-de-prueba'


class WebhookRededocTests(TenantTestCase):

    def setUp(self):
        # En `setUp` y no como decorador de la clase: `TenantTestCase` redefine
        # `setUpClass` y el `override_settings` de clase no llega a activarse.
        ajustes = override_settings(REDEDOC_WEBHOOK_SECRETO=SECRETO, REDEDOC_WEBHOOK_SECRETO_ANTERIOR='')
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        # El throttle cuenta en la caché del proceso, que sobrevive entre pruebas.
        cache.clear()
        tipo = GenDocumentoTipo.objects.create(
            id=1, nombre='FACTURA', documento_clase=GenDocumentoClase.objects.create(id=100, nombre='FV'),
        )
        self.electronico_id = uuid.uuid4()
        self.documento = GenDocumento.objects.create(
            documento_tipo=tipo, fecha=date(2026, 9, 21),
            estado_aprobado=True, estado_electronico_enviado=True, electronico_id=self.electronico_id,
        )
        self.factory = APIRequestFactory()

    def _enviar(self, crudo, fecha=None, firma=None, secreto=SECRETO):
        """Manda `crudo` tal cual; sin `firma` explícita, lo firma con `secreto`."""
        fecha = str(int(time.time())) if fecha is None else fecha
        if firma is None:
            firma = firmar_aviso(crudo, fecha, secreto)
        headers = {}
        if fecha:
            headers['HTTP_X_REDEDOC_FECHA'] = fecha
        if firma:
            headers['HTTP_X_REDEDOC_FIRMA'] = firma
        # Los `permission_classes` y `authentication_classes` del `@action` los
        # pasa el router como initkwargs; se pasan igual acá para probar la vista
        # tal como se publica, sin sesión.
        vista = CtnRededocViewSet.as_view({'post': 'webhook'}, **CtnRededocViewSet.webhook.kwargs)
        peticion = self.factory.post(
            '/contenedor/rededoc/webhook/', crudo, content_type='application/json', **headers,
        )
        return vista(peticion)

    def _cuerpo(self, **datos):
        cuerpo = {'cliente': self.tenant.id, 'documento': str(self.electronico_id)}
        cuerpo.update(datos)
        cuerpo = {k: v for k, v in cuerpo.items() if v is not None}
        return json.dumps(cuerpo).encode()

    def _llamar(self, **datos):
        return self._enviar(self._cuerpo(**datos))

    def _validacion(self, **datos):
        return self._llamar(**{
            'tipo': 'validacion', 'fecha_validacion': '2026-09-21T10:15:00-05:00', 'cufe': 'abc123',
            **datos,
        })

    def test_la_validacion_marca_el_documento_con_cufe_y_fecha(self):
        respuesta = self._validacion()

        self.assertEqual(respuesta.status_code, 200)
        self.documento.refresh_from_db()
        self.assertTrue(self.documento.estado_electronico)
        self.assertEqual(self.documento.cue, 'abc123')
        self.assertEqual(
            self.documento.fecha_validacion,
            timezone.make_aware(datetime(2026, 9, 21, 10, 15)),
        )
        self.assertFalse(self.documento.estado_electronico_notificado)

    def test_la_notificacion_marca_notificado(self):
        respuesta = self._llamar(tipo='notificacion')

        self.assertEqual(respuesta.status_code, 200)
        self.documento.refresh_from_db()
        self.assertTrue(self.documento.estado_electronico_notificado)
        self.assertFalse(self.documento.estado_electronico)

    def test_validar_un_documento_ya_validado_es_error_y_no_lo_reescribe(self):
        self._validacion()
        respuesta = self._validacion(cufe='otro', fecha_validacion='2026-09-22T08:00:00-05:00')

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data, {'detail': 'El documento ya estaba validado.'})
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.cue, 'abc123')
        self.assertEqual(
            self.documento.fecha_validacion,
            timezone.make_aware(datetime(2026, 9, 21, 10, 15)),
        )

    def test_repetir_la_notificacion_deja_el_documento_igual(self):
        self._llamar(tipo='notificacion')
        respuesta = self._llamar(tipo='notificacion')

        self.assertEqual(respuesta.status_code, 200)
        self.documento.refresh_from_db()
        self.assertTrue(self.documento.estado_electronico_notificado)

    def test_una_validacion_sin_cufe_ni_fecha_no_marca_nada(self):
        respuesta = self._validacion(cufe=None, fecha_validacion=None)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)
        self.assertIn('cufe', respuesta.data)
        self.assertIn('fecha_validacion', respuesta.data)
        self.documento.refresh_from_db()
        self.assertFalse(self.documento.estado_electronico)

    def test_una_fecha_sin_hora_no_se_acepta(self):
        respuesta = self._validacion(fecha_validacion='2026-09-21')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('fecha y hora', respuesta.data['detail'])
        self.documento.refresh_from_db()
        self.assertFalse(self.documento.estado_electronico)

    def test_un_tipo_desconocido_responde_400(self):
        respuesta = self._llamar(tipo='anulacion')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('tipo', respuesta.data)

    def test_un_documento_que_no_es_uuid_responde_400(self):
        respuesta = self._llamar(tipo='notificacion', documento='7')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('documento', respuesta.data)

    def test_un_documento_desconocido_responde_404(self):
        respuesta = self._llamar(tipo='notificacion', documento=str(uuid.uuid4()))
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta.data, {'detail': 'El documento no existe.'})

    def test_un_cliente_desconocido_responde_igual_que_un_documento_desconocido(self):
        """Mismo 404 y mismo mensaje: el webhook no revela qué clientes existen."""
        respuesta = self._llamar(tipo='notificacion', cliente=999999)
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta.data, {'detail': 'El documento no existe.'})

    # ---- firma ----

    def test_sin_firma_responde_401_y_no_marca(self):
        respuesta = self._enviar(self._cuerpo(tipo='notificacion'), fecha='', firma='')

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.data, {'detail': 'Firma inválida.'})
        self.documento.refresh_from_db()
        self.assertFalse(self.documento.estado_electronico_notificado)

    def test_firmado_con_otro_secreto_responde_401(self):
        respuesta = self._enviar(self._cuerpo(tipo='notificacion'), secreto='otro')
        self.assertEqual(respuesta.status_code, 401)

    def test_un_cuerpo_alterado_despues_de_firmar_responde_401(self):
        """Cambiar el `cliente` (o cualquier byte) invalida la firma."""
        fecha = str(int(time.time()))
        firma = firmar_aviso(self._cuerpo(tipo='notificacion'), fecha, SECRETO)
        alterado = self._cuerpo(tipo='notificacion', cliente=999999)

        respuesta = self._enviar(alterado, fecha=fecha, firma=firma)

        self.assertEqual(respuesta.status_code, 401)

    def test_un_aviso_viejo_responde_401_aunque_la_firma_cuadre(self):
        """Un aviso capturado no se puede reenviar pasados cinco minutos."""
        fecha = str(int(time.time()) - 301)
        respuesta = self._enviar(self._cuerpo(tipo='notificacion'), fecha=fecha)
        self.assertEqual(respuesta.status_code, 401)

    def test_una_fecha_que_no_es_numero_responde_401(self):
        respuesta = self._enviar(self._cuerpo(tipo='notificacion'), fecha='ayer')
        self.assertEqual(respuesta.status_code, 401)

    def test_la_firma_se_revisa_antes_que_el_cuerpo(self):
        """Sin firma válida no se valida nada: ni siquiera se dice qué campo falta."""
        respuesta = self._enviar(b'{}', secreto='otro')
        self.assertEqual(respuesta.status_code, 401)

    @override_settings(REDEDOC_WEBHOOK_SECRETO='nuevo', REDEDOC_WEBHOOK_SECRETO_ANTERIOR=SECRETO)
    def test_mientras_se_rota_se_acepta_el_secreto_anterior(self):
        self.assertEqual(self._enviar(self._cuerpo(tipo='notificacion'), secreto=SECRETO).status_code, 200)
        self.assertEqual(self._enviar(self._cuerpo(tipo='notificacion'), secreto='nuevo').status_code, 200)

    @override_settings(REDEDOC_WEBHOOK_SECRETO='', REDEDOC_WEBHOOK_SECRETO_ANTERIOR='')
    def test_sin_secreto_configurado_rechaza_todo(self):
        """Mejor rechazar que aceptar avisos sin verificar."""
        respuesta = self._enviar(self._cuerpo(tipo='notificacion'), secreto='')
        self.assertEqual(respuesta.status_code, 401)

    # ---- notificación programada ----

    def test_la_validacion_programa_la_notificacion_al_confirmar(self):
        with mock.patch('general.tasks.notificar_documento.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self._validacion()

        self.assertEqual(respuesta.status_code, 200)
        delay.assert_called_once_with(self.tenant.schema_name, self.documento.id)

    def test_la_notificacion_no_se_programa_antes_de_confirmar(self):
        """Encolar antes del commit dejaría al worker leer el documento sin validar."""
        with mock.patch('general.tasks.notificar_documento.delay') as delay:
            with self.captureOnCommitCallbacks(execute=False) as pendientes:
                self._validacion()

        delay.assert_not_called()
        self.assertEqual(len(pendientes), 1)

    def test_con_el_broker_caido_la_validacion_responde_200_y_queda_guardada(self):
        """Un error acá haría que rededoc reintente y reciba 409: la notificación se perdería."""
        with mock.patch('general.tasks.notificar_documento.delay', side_effect=ConnectionRefusedError()):
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self._validacion()

        self.assertEqual(respuesta.status_code, 200)
        self.documento.refresh_from_db()
        self.assertTrue(self.documento.estado_electronico)

    def test_la_notificacion_de_rededoc_no_programa_otra(self):
        with mock.patch('general.tasks.notificar_documento.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                self._llamar(tipo='notificacion')
        delay.assert_not_called()

    def test_una_validacion_repetida_no_programa_otra(self):
        self._validacion()
        with mock.patch('general.tasks.notificar_documento.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self._validacion()

        self.assertEqual(respuesta.status_code, 409)
        delay.assert_not_called()

    # ---- límite de peticiones ----

    def test_tiene_su_propio_limite_de_600_por_minuto(self):
        self.assertEqual(CtnRededocViewSet.webhook.kwargs['throttle_classes'], [ScopedRateThrottle])
        self.assertEqual(CtnRededocViewSet.throttle_scope, 'rededoc_webhook')
        self.assertEqual(ScopedRateThrottle.THROTTLE_RATES['rededoc_webhook'], '600/min')

    def test_pasado_el_limite_responde_429_con_detail(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'rededoc_webhook': '2/min'}):
            respuestas = [self._llamar(tipo='notificacion').status_code for _ in range(3)]
            ultima = self._llamar(tipo='notificacion')

        self.assertEqual(respuestas, [200, 200, 429])
        self.assertEqual(ultima.status_code, 429)
        self.assertIn('detail', ultima.data)

    def test_el_limite_del_webhook_no_es_el_anonimo_general(self):
        """Con el `anon` de 60/min, un lote de 61 validaciones ya recibía 429."""
        for _ in range(61):
            self.assertEqual(self._llamar(tipo='notificacion').status_code, 200)
