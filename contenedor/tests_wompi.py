"""
Pruebas de la firma del webhook de Wompi (`POST /contenedor/evento-pago/webhook-wompi/`).

Antes no se verificaba nada: cualquiera que conociera la URL podía mandar un
`APPROVED` inventado y extender una suscripción sin pagar.
"""

import hashlib
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import override_settings
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIRequestFactory

from contenedor.models import CtnEventoPago
from contenedor.views.evento_pago import CtnEventoPagoViewSet, firma_wompi_valida

SECRETO = 'test_events_secreto'
PROPIEDADES = ['transaction.id', 'transaction.status', 'transaction.amount_in_cents']


def evento(estado='DECLINED', transaccion='1234-1610641025-49201', monto=4490000,
           timestamp=1530291411, secreto=SECRETO, mayusculas=True):
    """Un evento como los de Wompi, firmado con `secreto`."""
    cuerpo = {
        'event': 'transaction.updated',
        'environment': 'test',
        'data': {'transaction': {
            'id': transaccion, 'status': estado, 'amount_in_cents': monto,
            'reference': 'x', 'customer_email': 'a@b.com',
        }},
        'timestamp': timestamp,
        'signature': {'properties': PROPIEDADES},
    }
    cadena = f'{transaccion}{estado}{monto}{timestamp}{secreto}'
    checksum = hashlib.sha256(cadena.encode()).hexdigest()
    cuerpo['signature']['checksum'] = checksum.upper() if mayusculas else checksum
    return cuerpo


class FirmaWompiTests(TenantTestCase):

    def setUp(self):
        # En `setUp`: el `override_settings` de clase no se activa en `TenantTestCase`.
        ajustes = override_settings(WOMPI_EVENTS_SECRET=SECRETO)
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        self.factory = APIRequestFactory()

    def _llamar(self, cuerpo):
        vista = CtnEventoPagoViewSet.as_view(
            {'post': 'webhook_wompi'}, **CtnEventoPagoViewSet.webhook_wompi.kwargs,
        )
        return vista(self.factory.post('/contenedor/evento-pago/webhook-wompi/', cuerpo, format='json'))

    # ---- la firma ----

    def test_un_evento_firmado_se_registra(self):
        respuesta = self._llamar(evento())

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(CtnEventoPago.objects.filter(transaccion='1234-1610641025-49201').count(), 1)

    def test_el_checksum_en_minusculas_tambien_vale(self):
        self.assertTrue(firma_wompi_valida(evento(mayusculas=False)))

    def test_sin_firma_responde_401_y_no_registra_nada(self):
        cuerpo = evento()
        del cuerpo['signature']

        respuesta = self._llamar(cuerpo)

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.data, {'detail': 'Firma inválida.'})
        self.assertFalse(CtnEventoPago.objects.exists())

    def test_firmado_con_otro_secreto_responde_401(self):
        self.assertEqual(self._llamar(evento(secreto='otro')).status_code, 401)
        self.assertFalse(CtnEventoPago.objects.exists())

    def test_un_aprobado_inventado_no_pasa(self):
        """El ataque que esto cierra: cambiar el estado de un evento a APPROVED."""
        cuerpo = evento(estado='DECLINED')
        cuerpo['data']['transaction']['status'] = 'APPROVED'

        self.assertEqual(self._llamar(cuerpo).status_code, 401)
        self.assertFalse(CtnEventoPago.objects.exists())

    def test_un_monto_alterado_no_pasa(self):
        cuerpo = evento()
        cuerpo['data']['transaction']['amount_in_cents'] = 1

        self.assertEqual(self._llamar(cuerpo).status_code, 401)

    def test_un_timestamp_alterado_no_pasa(self):
        cuerpo = evento()
        cuerpo['timestamp'] += 1

        self.assertEqual(self._llamar(cuerpo).status_code, 401)

    def test_sin_secreto_configurado_rechaza_todo(self):
        """Mejor rechazar que aceptar eventos sin verificar."""
        with override_settings(WOMPI_EVENTS_SECRET=''):
            self.assertEqual(self._llamar(evento(secreto='')).status_code, 401)
        self.assertFalse(CtnEventoPago.objects.exists())

    def test_propiedades_vacias_no_pasan(self):
        cuerpo = evento()
        cuerpo['signature']['properties'] = []
        self.assertFalse(firma_wompi_valida(cuerpo))

    # ---- reenvío ----

    def test_una_transaccion_aprobada_no_se_aplica_dos_veces(self):
        """Un evento legítimo reenviado —por Wompi o por un atacante— no extiende otra vez."""
        CtnEventoPago.objects.create(transaccion='1234-1610641025-49201', estado='APPROVED')

        with mock.patch('contenedor.views.evento_pago.CtnSuscripcion.objects') as suscripciones:
            respuesta = self._llamar(evento(estado='APPROVED'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(CtnEventoPago.objects.filter(transaccion='1234-1610641025-49201').count(), 1)
        suscripciones.select_related.assert_not_called()

    # ---- restricción única ----

    def test_la_base_no_admite_dos_aprobaciones_de_la_misma_transaccion(self):
        CtnEventoPago.objects.create(transaccion='T1', estado='APPROVED')

        with self.assertRaises(IntegrityError), transaction.atomic():
            CtnEventoPago.objects.create(transaccion='T1', estado='APPROVED')

    def test_los_demas_estados_si_se_pueden_repetir(self):
        """Pendiente y rechazado no aplican nada: Wompi puede mandarlos varias veces."""
        CtnEventoPago.objects.create(transaccion='T1', estado='PENDING')
        CtnEventoPago.objects.create(transaccion='T1', estado='PENDING')
        CtnEventoPago.objects.create(transaccion='T1', estado='APPROVED')

        self.assertEqual(CtnEventoPago.objects.filter(transaccion='T1').count(), 3)

    def test_dos_entregas_simultaneas_aplican_una_sola_vez(self):
        """
        La otra entrega ya se aplicó entre la revisión y el INSERT: la revisión no la
        ve (se simula con `exists` en falso) y la restricción es la que la frena.
        """
        CtnEventoPago.objects.create(transaccion='1234-1610641025-49201', estado='APPROVED')

        with mock.patch('django.db.models.query.QuerySet.exists', return_value=False):
            respuesta = self._llamar(evento(estado='APPROVED'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            CtnEventoPago.objects.filter(transaccion='1234-1610641025-49201', estado='APPROVED').count(), 1,
        )
