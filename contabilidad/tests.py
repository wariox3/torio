from datetime import date
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from rest_framework.exceptions import ValidationError

from contabilidad.models import (
    ConCentroCosto,
    ConComprobante,
    ConCuenta,
    ConMovimiento,
    ConPeriodo,
)
from contabilidad.servicios import contabilizar
from contabilidad.views.comprobante import ConComprobanteViewSet
from contabilidad.views.cuenta import ConCuentaViewSet
from contabilidad.views.movimiento_informe import ConMovimientoInformeViewSet
from general.models import (
    GenCuentaBanco,
    GenCuentaBancoTipo,
    GenDocumento,
    GenDocumentoDetalle,
    GenDocumentoPago,
    GenDocumentoTipo,
    GenItem,
    GenSede,
)


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


class _ContabilizarBase(TenantTestCase):
    """Montaje común de las pruebas de contabilización: plan de cuentas y tipos."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.comprobante = ConComprobante.objects.create(id=1, nombre='Comprobante')
        self.periodo = ConPeriodo.objects.create(anio=2026, mes=1)

        self.cuenta_cobrar = ConCuenta.objects.create(
            codigo='1305', nombre='Clientes', permite_movimiento=True,
        )
        self.cuenta_venta = ConCuenta.objects.create(
            codigo='4135', nombre='Ingresos', permite_movimiento=True,
        )
        self.cuenta_pagar = ConCuenta.objects.create(
            codigo='2205', nombre='Proveedores', permite_movimiento=True,
        )
        self.cuenta_gasto = ConCuenta.objects.create(
            codigo='5135', nombre='Gastos', permite_movimiento=True,
        )

        # Ids propios y fuera del rango que el servicio reserva (PAGO, EGRESO,
        # ASIENTO, NOMINA, PRIMA, SEGURIDAD SOCIAL, CIERRE): con ids
        # autogenerados una prueba caería sobre uno de ellos y tomaría su rama.
        self.factura_tipo = self._crear_tipo(901, 'FACTURA', operacion=1, venta=True, cobrar=True)
        self.nota_credito_tipo = self._crear_tipo(902, 'NOTA CREDITO', operacion=-1, venta=True, cobrar=True)
        self.compra_tipo = self._crear_tipo(903, 'COMPRA', operacion=1, compra=True, pagar=True)

    def _crear_tipo(self, pk, nombre, operacion, venta=False, compra=False, cobrar=False, pagar=False):
        return GenDocumentoTipo.objects.create(
            pk=pk,
            nombre=nombre,
            operacion=operacion,
            venta=venta,
            compra=compra,
            cobrar=cobrar,
            pagar=pagar,
            comprobante=self.comprobante,
            cuenta_cobrar=self.cuenta_cobrar,
            cuenta_pagar=self.cuenta_pagar,
        )

    def _crear_documento(self, documento_tipo, total='100', **extra):
        datos = {
            'documento_tipo': documento_tipo,
            'fecha': date(2026, 1, 15),
            'fecha_contable': date(2026, 1, 15),
            'numero': 1,
            'total': Decimal(total),
            'estado_aprobado': True,
        }
        datos.update(extra)
        return GenDocumento.objects.create(**datos)

    def _crear_detalle_item(self, documento, item, subtotal='100'):
        return GenDocumentoDetalle.objects.create(
            documento=documento, item=item, tipo_registro='I',
            cantidad=1, precio=Decimal(subtotal), subtotal=Decimal(subtotal),
            total=Decimal(subtotal),
        )

    def _crear_item(self):
        return GenItem.objects.create(
            nombre='Item', cuenta_venta=self.cuenta_venta, cuenta_compra=self.cuenta_gasto,
        )

    def _movimientos(self, documento):
        return list(ConMovimiento.objects.filter(documento=documento).order_by('id'))


class ContabilizarTests(_ContabilizarBase):
    """
    Contabilizar deriva el asiento del documento: la naturaleza sale del signo de
    `GenDocumentoTipo.operacion` y no de listas de ids, el lote es atómico y el
    periodo se valida antes de escribir nada.
    """

    # ------------------------------------------------------------- asiento ----

    def test_una_factura_debita_el_cliente_y_acredita_el_ingreso(self):
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        movimientos = self._movimientos(documento)
        por_cuenta = {m.cuenta_id: m for m in movimientos}
        self.assertEqual(por_cuenta[self.cuenta_cobrar.pk].naturaleza, 'D')
        self.assertEqual(por_cuenta[self.cuenta_cobrar.pk].debito, Decimal('100'))
        self.assertEqual(por_cuenta[self.cuenta_venta.pk].naturaleza, 'C')
        self.assertEqual(por_cuenta[self.cuenta_venta.pk].credito, Decimal('100'))

    def test_el_asiento_cuadra(self):
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        movimientos = self._movimientos(documento)
        self.assertEqual(
            sum(m.debito for m in movimientos), sum(m.credito for m in movimientos),
        )

    def test_la_nota_credito_invierte_la_naturaleza(self):
        """Mismo asiento que la factura pero al revés, por `operacion = -1`."""
        documento = self._crear_documento(self.nota_credito_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        por_cuenta = {m.cuenta_id: m for m in self._movimientos(documento)}
        self.assertEqual(por_cuenta[self.cuenta_cobrar.pk].naturaleza, 'C')
        self.assertEqual(por_cuenta[self.cuenta_venta.pk].naturaleza, 'D')

    def test_una_compra_acredita_el_proveedor_y_debita_el_gasto(self):
        documento = self._crear_documento(self.compra_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        por_cuenta = {m.cuenta_id: m for m in self._movimientos(documento)}
        self.assertEqual(por_cuenta[self.cuenta_pagar.pk].naturaleza, 'C')
        self.assertEqual(por_cuenta[self.cuenta_gasto.pk].naturaleza, 'D')

    def test_el_pago_registrado_reduce_lo_que_queda_en_cartera(self):
        cuenta_banco_contable = ConCuenta.objects.create(
            codigo='1110', nombre='Banco', permite_movimiento=True,
        )
        cuenta_banco = GenCuentaBanco.objects.create(
            nombre='Banco', cuenta=cuenta_banco_contable,
            cuenta_banco_tipo=GenCuentaBancoTipo.objects.create(nombre='Ahorros'),
        )
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())
        GenDocumentoPago.objects.create(
            documento=documento, cuenta_banco=cuenta_banco, pago=Decimal('40'),
        )

        contabilizar.contabilizar([documento.pk])

        por_cuenta = {m.cuenta_id: m for m in self._movimientos(documento)}
        self.assertEqual(por_cuenta[cuenta_banco_contable.pk].debito, Decimal('40'))
        self.assertEqual(por_cuenta[self.cuenta_cobrar.pk].debito, Decimal('60'))

    def test_el_pago_anulado_no_genera_movimiento(self):
        cuenta_banco_contable = ConCuenta.objects.create(
            codigo='1110', nombre='Banco', permite_movimiento=True,
        )
        cuenta_banco = GenCuentaBanco.objects.create(
            nombre='Banco', cuenta=cuenta_banco_contable,
            cuenta_banco_tipo=GenCuentaBancoTipo.objects.create(nombre='Ahorros'),
        )
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())
        GenDocumentoPago.objects.create(
            documento=documento, cuenta_banco=cuenta_banco, pago=Decimal('40'),
            estado_anulado=True,
        )

        contabilizar.contabilizar([documento.pk])

        por_cuenta = {m.cuenta_id: m for m in self._movimientos(documento)}
        self.assertNotIn(cuenta_banco_contable.pk, por_cuenta)
        self.assertEqual(por_cuenta[self.cuenta_cobrar.pk].debito, Decimal('100'))

    def test_el_centro_de_costo_solo_se_guarda_si_la_cuenta_lo_exige(self):
        centro_costo = ConCentroCosto.objects.create(nombre='Centro')
        self.cuenta_venta.exige_centro_costo = True
        self.cuenta_venta.save(update_fields=['exige_centro_costo'])
        sede = GenSede.objects.create(nombre='Sede', centro_costo=centro_costo)
        documento = self._crear_documento(self.factura_tipo, sede=sede)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        por_cuenta = {m.cuenta_id: m for m in self._movimientos(documento)}
        self.assertEqual(por_cuenta[self.cuenta_venta.pk].centro_costo_id, centro_costo.pk)
        self.assertIsNone(por_cuenta[self.cuenta_cobrar.pk].centro_costo_id)

    def test_el_movimiento_guarda_cuando_se_contabilizo(self):
        """
        `bulk_create` no dispara los signals de `gen_log`, así que la marca de
        creación tiene que estar en la propia fila.
        """
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        for movimiento in self._movimientos(documento):
            self.assertIsNotNone(movimiento.fecha_creacion)
            # Fuera de un request no hay usuario en contexto.
            self.assertIsNone(movimiento.usuario_id)

    # ---------------------------------------------------------- validación ----

    def test_rechaza_un_documento_sin_aprobar(self):
        documento = self._crear_documento(self.factura_tipo, estado_aprobado=False)

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_rechaza_un_documento_ya_contabilizado(self):
        documento = self._crear_documento(self.factura_tipo, estado_contabilizado=True)

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_rechaza_un_periodo_bloqueado(self):
        self.periodo.estado_bloqueado = True
        self.periodo.save(update_fields=['estado_bloqueado'])
        documento = self._crear_documento(self.factura_tipo)

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_rechaza_un_periodo_que_no_existe(self):
        documento = self._crear_documento(
            self.factura_tipo, fecha_contable=date(2030, 6, 1),
        )

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_una_fecha_contable_vacia_da_error_de_validacion(self):
        """Sin fecha no hay periodo: tiene que decirlo, no fallar al derivarlo."""
        documento = self._crear_documento(self.factura_tipo, fecha_contable=None)

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_rechaza_un_tipo_sin_comprobante(self):
        self.factura_tipo.comprobante = None
        self.factura_tipo.save(update_fields=['comprobante'])
        documento = self._crear_documento(self.factura_tipo)

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_rechaza_un_tipo_con_operacion_en_cero(self):
        """En cero la naturaleza saldría acreditada para todo, sin que nadie lo note."""
        self.factura_tipo.operacion = 0
        self.factura_tipo.save(update_fields=['operacion'])
        documento = self._crear_documento(self.factura_tipo)

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    # ------------------------------------------------------------- el lote ----

    def test_si_un_documento_del_lote_falla_no_queda_ninguno_contabilizado(self):
        bueno = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(bueno, self._crear_item())
        malo = self._crear_documento(self.factura_tipo, estado_aprobado=False)

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([bueno.pk, malo.pk])

        bueno.refresh_from_db()
        self.assertFalse(bueno.estado_contabilizado)
        self.assertEqual(ConMovimiento.objects.filter(documento=bueno).count(), 0)

    def test_un_documento_anulado_se_marca_sin_generar_movimientos(self):
        documento = self._crear_documento(self.factura_tipo, estado_anulado=True)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        documento.refresh_from_db()
        self.assertTrue(documento.estado_contabilizado)
        self.assertEqual(self._movimientos(documento), [])


class DescontabilizarTests(_ContabilizarBase):
    """Descontabilizar deshace exactamente lo que hizo contabilizar."""

    def test_borra_los_movimientos_y_quita_el_contabilizado(self):
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())
        contabilizar.contabilizar([documento.pk])

        contabilizar.descontabilizar([documento.pk])

        documento.refresh_from_db()
        self.assertFalse(documento.estado_contabilizado)
        self.assertEqual(self._movimientos(documento), [])

    def test_rechaza_un_documento_que_no_esta_contabilizado(self):
        documento = self._crear_documento(self.factura_tipo)

        with self.assertRaises(ValidationError):
            contabilizar.descontabilizar([documento.pk])

    def test_rechaza_un_periodo_bloqueado(self):
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())
        contabilizar.contabilizar([documento.pk])
        self.periodo.estado_bloqueado = True
        self.periodo.save(update_fields=['estado_bloqueado'])

        with self.assertRaises(ValidationError):
            contabilizar.descontabilizar([documento.pk])

    def test_el_periodo_sale_de_los_movimientos_y_no_de_la_fecha(self):
        """
        Un cierre se contabiliza en el periodo 13, no en el de su mes. Si el
        periodo se recalculara desde la fecha, se buscaría uno que no es el que se
        afectó y el documento no se podría descontabilizar.
        """
        periodo_ajustes = ConPeriodo.objects.create(anio=2026, mes=13)
        cierre_tipo = GenDocumentoTipo.objects.create(
            pk=contabilizar.DOCUMENTO_TIPO_CIERRE, nombre='CIERRE CONTABLE',
            operacion=1, comprobante=self.comprobante,
        )
        documento = GenDocumento.objects.create(
            documento_tipo=cierre_tipo, fecha=date(2026, 1, 15),
            fecha_contable=date(2026, 1, 15), numero=1, estado_aprobado=True,
        )
        GenDocumentoDetalle.objects.create(
            documento=documento, tipo_registro='C', cuenta=self.cuenta_venta,
            naturaleza='D', precio=Decimal('50'),
        )

        contabilizar.contabilizar([documento.pk])
        movimiento = ConMovimiento.objects.filter(documento=documento).first()
        self.assertEqual(movimiento.periodo_id, periodo_ajustes.pk)
        self.assertTrue(movimiento.cierre)

        contabilizar.descontabilizar([documento.pk])

        documento.refresh_from_db()
        self.assertFalse(documento.estado_contabilizado)
