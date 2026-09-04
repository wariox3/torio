from datetime import date

from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from contabilidad.models import ConComprobante, ConCuenta, ConMovimiento, ConPeriodo
from contabilidad.views.comprobante import ConComprobanteViewSet
from contabilidad.views.cuenta import ConCuentaViewSet
from general.models import GenDocumento, GenDocumentoDetalle, GenDocumentoTipo


class _CuentaViewSinPermisos(ConCuentaViewSet):
    """Variante de la vista sin auth/permiso/throttle para probar el action aislado."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class TrasladarCuentaTests(TenantTestCase):
    """
    El traslado reasigna a la cuenta destino los movimientos y los detalles de
    documento de la cuenta origen, y no toca los de ninguna otra cuenta.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.factory = APIRequestFactory()

        self.origen = self._crear_cuenta('1105')
        self.destino = self._crear_cuenta('1110')
        self.ajena = self._crear_cuenta('1120')

        self.comprobante = ConComprobante.objects.create(id=1, nombre='Comprobante')
        self.periodo = ConPeriodo.objects.create(anio=2026, mes=1)
        self.documento = GenDocumento.objects.create(
            documento_tipo=GenDocumentoTipo.objects.create(nombre='Factura'),
            fecha=date(2026, 1, 1),
        )

    def _crear_cuenta(self, codigo, permite_movimiento=True):
        return ConCuenta.objects.create(
            codigo=codigo, nombre=f'Cuenta {codigo}', permite_movimiento=permite_movimiento,
        )

    def _crear_movimiento(self, cuenta):
        return ConMovimiento.objects.create(
            fecha=date(2026, 1, 15),
            naturaleza='D',
            comprobante=self.comprobante,
            periodo=self.periodo,
            cuenta=cuenta,
        )

    def _crear_detalle(self, cuenta):
        return GenDocumentoDetalle.objects.create(documento=self.documento, cuenta=cuenta)

    def _post(self, **payload):
        view = _CuentaViewSinPermisos.as_view({'post': 'trasladar'})
        return view(self.factory.post('/cuenta/trasladar/', payload, format='json'))

    def test_traslada_movimientos_y_detalles(self):
        self._crear_movimiento(self.origen)
        self._crear_movimiento(self.origen)
        self._crear_detalle(self.origen)

        response = self._post(cuenta_origen=self.origen.id, cuenta_destino=self.destino.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'movimientos': 2, 'documentos_detalles': 1})
        self.assertEqual(ConMovimiento.objects.filter(cuenta=self.origen).count(), 0)
        self.assertEqual(ConMovimiento.objects.filter(cuenta=self.destino).count(), 2)
        self.assertEqual(GenDocumentoDetalle.objects.filter(cuenta=self.origen).count(), 0)
        self.assertEqual(GenDocumentoDetalle.objects.filter(cuenta=self.destino).count(), 1)

    def test_no_toca_registros_de_otras_cuentas(self):
        self._crear_movimiento(self.origen)
        movimiento_ajeno = self._crear_movimiento(self.ajena)
        detalle_ajeno = self._crear_detalle(self.ajena)

        response = self._post(cuenta_origen=self.origen.id, cuenta_destino=self.destino.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['movimientos'], 1)
        movimiento_ajeno.refresh_from_db()
        detalle_ajeno.refresh_from_db()
        self.assertEqual(movimiento_ajeno.cuenta_id, self.ajena.id)
        self.assertEqual(detalle_ajeno.cuenta_id, self.ajena.id)

    def test_traslada_sin_registros(self):
        response = self._post(cuenta_origen=self.origen.id, cuenta_destino=self.destino.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'movimientos': 0, 'documentos_detalles': 0})

    def test_rechaza_cuentas_iguales(self):
        movimiento = self._crear_movimiento(self.origen)

        response = self._post(cuenta_origen=self.origen.id, cuenta_destino=self.origen.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        movimiento.refresh_from_db()
        self.assertEqual(movimiento.cuenta_id, self.origen.id)

    def test_rechaza_destino_que_no_permite_movimiento(self):
        destino = self._crear_cuenta('1115', permite_movimiento=False)
        movimiento = self._crear_movimiento(self.origen)

        response = self._post(cuenta_origen=self.origen.id, cuenta_destino=destino.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        movimiento.refresh_from_db()
        self.assertEqual(movimiento.cuenta_id, self.origen.id)

    def test_permite_origen_que_no_permite_movimiento(self):
        # Una cuenta ya inhabilitada con histórico es justo lo que se quiere trasladar.
        origen = self._crear_cuenta('1125', permite_movimiento=False)
        self._crear_movimiento(origen)

        response = self._post(cuenta_origen=origen.id, cuenta_destino=self.destino.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['movimientos'], 1)

    def test_rechaza_cuenta_inexistente(self):
        response = self._post(cuenta_origen=self.origen.id, cuenta_destino=99999)

        self.assertEqual(response.status_code, 400)
        self.assertIn('cuenta_destino', response.data)

    def test_rechaza_parametros_faltantes(self):
        response = self._post(cuenta_origen=self.origen.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('cuenta_destino', response.data)


class _ComprobanteViewSinPermisos(ConComprobanteViewSet):
    """Variante de la vista sin auth/permiso/throttle para probar el action aislado."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class SeleccionarComprobanteTests(TenantTestCase):
    """
    De los 24 comprobantes del catálogo solo AJUSTE CONTABLE admite asiento manual,
    así que el selector del front necesita poder acotarse: sin el filtro le ofrece
    al usuario 23 comprobantes que no puede usar.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.ajuste = ConComprobante.objects.create(
            id=10, nombre='AJUSTE CONTABLE', codigo='AJU', permite_asiento=True,
        )
        self.venta = ConComprobante.objects.create(id=4, nombre='VENTA', codigo='VEN')

    def _seleccionar(self, params=None):
        request = APIRequestFactory().get('/contabilidad/comprobante/seleccionar/', params or {})
        response = _ComprobanteViewSinPermisos.as_view({'get': 'seleccionar'})(request)
        self.assertEqual(response.status_code, 200)
        return [c['id'] for c in response.data['results']]

    def test_sin_el_parametro_los_lista_todos(self):
        self.assertEqual(sorted(self._seleccionar()), [4, 10])

    def test_filtra_los_que_permiten_asiento(self):
        self.assertEqual(self._seleccionar({'permite_asiento': 'true'}), [10])

    def test_filtra_los_que_no_permiten_asiento(self):
        self.assertEqual(self._seleccionar({'permite_asiento': 'false'}), [4])

    def test_el_search_no_recupera_uno_excluido(self):
        """
        El `search` arma un OR sobre el queryset; si el filtro se aplicara después,
        buscar 'VEN' devolvería VENTA aunque no permita asiento.
        """
        self.assertEqual(self._seleccionar({'permite_asiento': 'true', 'search': 'VEN'}), [])
