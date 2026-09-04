from datetime import date
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from contabilidad.models import (
    ConCentroCosto,
    ConComprobante,
    ConCuenta,
    ConMovimiento,
    ConPeriodo,
)
from contabilidad.views.comprobante import ConComprobanteViewSet
from contabilidad.views.cuenta import ConCuentaViewSet
from contabilidad.views.movimiento_informe import ConMovimientoInformeViewSet
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


class _MovimientoInformeViewSinPermisos(ConMovimientoInformeViewSet):
    """Variante de la vista sin auth/permiso/throttle para probar los actions aislados."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class BalancePruebaTests(TenantTestCase):
    """
    El balance parte el histórico de `con_movimiento` en dos por la fecha de
    corte: lo anterior al rango llega neteado como saldo anterior y lo que cae
    dentro como débito y crédito del periodo. Ningún saldo está guardado — todo
    sale de sumar los movimientos — así que estas pruebas son la única red que
    detecta un corte mal puesto.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.comprobante = ConComprobante.objects.create(id=1, nombre='Comprobante')
        self.periodo = ConPeriodo.objects.create(anio=2026, mes=1)
        self.anterior = ConPeriodo.objects.create(anio=2025, mes=12)
        self.caja = self._cuenta('1105')
        self.banco = self._cuenta('1110')
        self.centro = ConCentroCosto.objects.create(nombre='Norte', codigo='N')

    def _cuenta(self, codigo):
        return ConCuenta.objects.create(
            codigo=codigo, nombre=f'Cuenta {codigo}', permite_movimiento=True,
        )

    def _movimiento(self, cuenta, fecha, debito=0, credito=0, centro_costo=None):
        return ConMovimiento.objects.create(
            fecha=fecha,
            debito=Decimal(debito),
            credito=Decimal(credito),
            naturaleza='D' if debito else 'C',
            comprobante=self.comprobante,
            periodo=self.anterior if fecha.year == 2025 else self.periodo,
            cuenta=cuenta,
            centro_costo=centro_costo,
        )

    def _post(self, accion, **payload):
        payload.setdefault('informe', 'balance_prueba')
        payload.setdefault('fecha_desde', '2026-01-01')
        payload.setdefault('fecha_hasta', '2026-01-31')
        request = APIRequestFactory().post(
            f'/contabilidad/movimiento-informe/{accion}/', payload, format='json',
        )
        return _MovimientoInformeViewSinPermisos.as_view({'post': accion})(request)

    def _lista(self, **payload):
        response = self._post('lista', **payload)
        self.assertEqual(response.status_code, 200)
        return response.data['results']

    def _totales(self, **payload):
        response = self._post('totales', **payload)
        self.assertEqual(response.status_code, 200)
        return {clave: Decimal(valor) for clave, valor in response.data.items()}

    def _fila(self, filas, codigo):
        return next(fila for fila in filas if fila['cuenta_codigo'] == codigo)

    def test_lo_anterior_al_rango_llega_como_saldo_anterior(self):
        self._movimiento(self.caja, date(2025, 12, 31), debito=100)
        self._movimiento(self.caja, date(2026, 1, 15), debito=40)

        fila = self._fila(self._lista(), '1105')

        self.assertEqual(Decimal(fila['saldo_anterior_debito']), Decimal(100))
        self.assertEqual(Decimal(fila['debito']), Decimal(40))
        self.assertEqual(Decimal(fila['credito']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_final_debito']), Decimal(140))

    def test_la_cuenta_sin_movimiento_en_el_rango_aparece_con_su_saldo(self):
        """
        Es la mitad del balance que se pierde si el saldo anterior se calcula
        sobre las cuentas que movieron en el rango: la cuenta quieta también
        tiene saldo y tiene que sumar al cuadre.
        """
        self._movimiento(self.banco, date(2025, 6, 30), debito=70)

        fila = self._fila(self._lista(), '1110')

        self.assertEqual(Decimal(fila['saldo_anterior_debito']), Decimal(70))
        self.assertEqual(Decimal(fila['debito']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_final_debito']), Decimal(70))

    def test_lo_posterior_al_rango_no_entra(self):
        self._movimiento(self.caja, date(2026, 1, 10), debito=30)
        self._movimiento(self.caja, date(2026, 2, 5), debito=999)

        fila = self._fila(self._lista(), '1105')

        self.assertEqual(Decimal(fila['debito']), Decimal(30))
        self.assertEqual(Decimal(fila['saldo_final_debito']), Decimal(30))

    def test_el_saldo_neto_negativo_va_en_la_columna_de_credito(self):
        self._movimiento(self.caja, date(2025, 12, 1), credito=80)
        self._movimiento(self.caja, date(2026, 1, 20), credito=20)

        fila = self._fila(self._lista(), '1105')

        self.assertEqual(Decimal(fila['saldo_anterior_debito']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_anterior_credito']), Decimal(80))
        self.assertEqual(Decimal(fila['saldo_final_credito']), Decimal(100))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(-100))

    def test_una_fila_por_cuenta(self):
        """
        `ConMovimiento.Meta.ordering` es `['-id']`, y sobre un queryset agrupado
        Django mete el campo de ordenamiento en el GROUP BY: sin el `order_by`
        explícito del servicio, esto devolvería tres filas de la misma cuenta.
        """
        for dia in (5, 10, 15):
            self._movimiento(self.caja, date(2026, 1, dia), debito=10)

        filas = self._lista()

        self.assertEqual(len(filas), 1)
        self.assertEqual(Decimal(filas[0]['debito']), Decimal(30))

    def test_los_totales_cuadran(self):
        self._movimiento(self.caja, date(2025, 12, 31), debito=200)
        self._movimiento(self.banco, date(2025, 12, 31), credito=200)
        self._movimiento(self.caja, date(2026, 1, 15), debito=50)
        self._movimiento(self.banco, date(2026, 1, 15), credito=50)

        totales = self._totales()

        self.assertEqual(totales['saldo_anterior_debito'], totales['saldo_anterior_credito'])
        self.assertEqual(totales['debito'], totales['credito'])
        self.assertEqual(totales['saldo_final_debito'], totales['saldo_final_credito'])
        self.assertEqual(totales['debito'], Decimal(50))
        self.assertEqual(totales['saldo_final_debito'], Decimal(250))

    def test_el_filtro_acota_tambien_el_saldo_anterior(self):
        """
        Los filtros se aplican antes de agrupar. Si se aplicaran después, el
        movimiento sin centro de costo saldría del rango pero seguiría contando
        en el saldo anterior, y el balance filtrado no cuadraría.
        """
        self._movimiento(self.caja, date(2025, 12, 1), debito=100, centro_costo=self.centro)
        self._movimiento(self.caja, date(2025, 12, 1), debito=500)
        self._movimiento(self.caja, date(2026, 1, 15), debito=10, centro_costo=self.centro)

        filas = self._lista(filtros=[
            {'propiedad': 'centro_costo_id', 'operador': '=', 'valor': self.centro.id},
        ])
        fila = self._fila(filas, '1105')

        self.assertEqual(Decimal(fila['saldo_anterior_debito']), Decimal(100))
        self.assertEqual(Decimal(fila['debito']), Decimal(10))

    def test_las_cuentas_salen_por_codigo(self):
        self._movimiento(self.banco, date(2026, 1, 5), debito=10)
        self._movimiento(self.caja, date(2026, 1, 5), debito=10)

        self.assertEqual([fila['cuenta_codigo'] for fila in self._lista()], ['1105', '1110'])

    def test_omite_la_cuenta_en_ceros(self):
        """
        La cuenta movió alguna vez, se canceló y no volvió a moverse: llega al
        rango con saldo cero y sin movimiento, así que es una fila de puros ceros
        que solo estorba en el balance.
        """
        self._movimiento(self.banco, date(2025, 3, 1), debito=90)
        self._movimiento(self.banco, date(2025, 4, 1), credito=90)
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)

        codigos = [fila['cuenta_codigo'] for fila in self._lista()]

        self.assertEqual(codigos, ['1105'])

    def test_con_solo_con_saldo_false_sale_la_cuenta_en_ceros(self):
        self._movimiento(self.banco, date(2025, 3, 1), debito=90)
        self._movimiento(self.banco, date(2025, 4, 1), credito=90)
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)

        filas = self._lista(solo_con_saldo=False)
        fila = self._fila(filas, '1110')

        self.assertEqual([f['cuenta_codigo'] for f in filas], ['1105', '1110'])
        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(0))

    def test_la_cuenta_que_movio_en_el_rango_y_quedo_en_cero_si_sale(self):
        """
        Netea cero pero movió dentro del rango: el débito y el crédito del periodo
        son parte del balance aunque el saldo final quede en cero.
        """
        self._movimiento(self.banco, date(2026, 1, 5), debito=60)
        self._movimiento(self.banco, date(2026, 1, 20), credito=60)

        fila = self._fila(self._lista(), '1110')

        self.assertEqual(Decimal(fila['debito']), Decimal(60))
        self.assertEqual(Decimal(fila['credito']), Decimal(60))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(0))

    def test_omitir_ceros_no_cambia_los_totales(self):
        """Una fila en ceros aporta cero a las seis columnas, con o sin la bandera."""
        self._movimiento(self.banco, date(2025, 3, 1), debito=90)
        self._movimiento(self.banco, date(2025, 4, 1), credito=90)
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)

        self.assertEqual(self._totales(), self._totales(solo_con_saldo=False))

    def test_no_acepta_ordenamientos(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=10)

        response = self._post('lista', ordenamientos=['-cuenta__codigo'])

        self.assertEqual(response.status_code, 400)
        self.assertIn('ordenamientos', response.data)

    def test_exige_el_rango(self):
        response = self._post('lista', fecha_desde=None)

        self.assertEqual(response.status_code, 400)
        self.assertIn('fecha_desde', response.data)

    def test_rechaza_un_rango_invertido(self):
        response = self._post('lista', fecha_desde='2026-02-01', fecha_hasta='2026-01-01')

        self.assertEqual(response.status_code, 400)
        self.assertIn('fecha_desde', response.data)

    def test_rechaza_un_informe_que_no_existe(self):
        response = self._post('lista', informe='inventado')

        self.assertEqual(response.status_code, 400)
        self.assertIn('informe', response.data)

    def test_el_excel_trae_una_fila_por_cuenta(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=10)
        self._movimiento(self.caja, date(2026, 1, 6), debito=10)

        response = self._post('excel')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('balance_prueba.xlsx', response['Content-Disposition'])
