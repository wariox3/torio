"""
Pruebas del webhook de rededoc (`POST /contenedor/rededoc/webhook/`).

Vive en el schema público y entra al del tenant por el `cliente` del aviso, así
que se prueba con un tenant real: el documento se crea en su schema y la vista
tiene que encontrarlo desde afuera.
"""

import uuid
from datetime import date, datetime

from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIRequestFactory

from contenedor.views.rededoc import CtnRededocViewSet
from general.models import GenDocumento, GenDocumentoClase, GenDocumentoTipo


class WebhookRededocTests(TenantTestCase):

    def setUp(self):
        tipo = GenDocumentoTipo.objects.create(
            id=1, nombre='FACTURA', documento_clase=GenDocumentoClase.objects.create(id=100, nombre='FV'),
        )
        self.electronico_id = uuid.uuid4()
        self.documento = GenDocumento.objects.create(
            documento_tipo=tipo, fecha=date(2026, 9, 21),
            estado_aprobado=True, estado_electronico_enviado=True, electronico_id=self.electronico_id,
        )
        self.factory = APIRequestFactory()

    def _llamar(self, **datos):
        cuerpo = {'cliente': self.tenant.id, 'documento': str(self.electronico_id)}
        cuerpo.update(datos)
        cuerpo = {k: v for k, v in cuerpo.items() if v is not None}
        # Los `permission_classes` y `authentication_classes` del `@action` los
        # pasa el router como initkwargs; se pasan igual acá para probar la vista
        # tal como se publica, sin sesión.
        vista = CtnRededocViewSet.as_view({'post': 'webhook'}, **CtnRededocViewSet.webhook.kwargs)
        return vista(self.factory.post('/contenedor/rededoc/webhook/', cuerpo, format='json'))

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
