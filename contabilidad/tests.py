from datetime import date
from decimal import Decimal
from io import BytesIO

from django_tenants.test.cases import TenantTestCase
from openpyxl import load_workbook
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from rest_framework.exceptions import ValidationError

from contabilidad.models import (
    ConCentroCosto,
    ConComprobante,
    ConCuenta,
    ConCuentaClase,
    ConCuentaCuenta,
    ConCuentaGrupo,
    ConMovimiento,
    ConPeriodo,
)
from contabilidad.servicios import contabilizar
from contabilidad.servicios.movimiento import analizar_inconsistencias
from contabilidad.views.comprobante import ConComprobanteViewSet
from contabilidad.views.cuenta import ConCuentaViewSet
from contabilidad.views.movimiento import ConMovimientoViewSet
from contabilidad.views.movimiento_informe import ConMovimientoInformeViewSet
from general.models import (
    GenCiudad,
    GenConfiguracion,
    GenContacto,
    GenCuentaBanco,
    GenCuentaBancoTipo,
    GenDocumento,
    GenDocumentoDetalle,
    GenDocumentoPago,
    GenDocumentoTipo,
    GenEstado,
    GenIdentificacion,
    GenItem,
    GenPais,
    GenSede,
    GenTipoPersona,
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


class _InformeBase(TenantTestCase):
    """
    Montaje común de los informes de contabilidad: dos cuentas del plan con su
    clase, su grupo y su cuenta, un comprobante y dos periodos.

    Las pruebas van por la API y no por el servicio, porque lo que hay que fijar
    es el contrato que ve el front: el mismo `POST /lista/` cambia de informe con
    un parámetro.
    """

    informe = None

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.comprobante = ConComprobante.objects.create(id=1, nombre='Comprobante')
        self.periodo = ConPeriodo.objects.create(anio=2026, mes=1)
        self.anterior = ConPeriodo.objects.create(anio=2025, mes=12)
        self.clase = ConCuentaClase.objects.create(id=1, nombre='Activo')
        self.grupo = ConCuentaGrupo.objects.create(id=11, nombre='Disponible')
        self.grupo_caja = ConCuentaCuenta.objects.create(id=1105, nombre='Caja')
        self.grupo_banco = ConCuentaCuenta.objects.create(id=1110, nombre='Bancos')
        self.caja = self._cuenta('11050505', self.grupo_caja)
        self.banco = self._cuenta('11100505', self.grupo_banco)
        self.centro = ConCentroCosto.objects.create(nombre='Norte', codigo='N')

    def _cuenta(self, codigo, cuenta_cuenta, exige_base=False, cuenta_clase=None,
                cuenta_grupo=None):
        return ConCuenta.objects.create(
            codigo=codigo, nombre=f'Cuenta {codigo}', permite_movimiento=True,
            exige_base=exige_base,
            cuenta_clase=cuenta_clase or self.clase,
            cuenta_grupo=cuenta_grupo or self.grupo,
            cuenta_cuenta=cuenta_cuenta,
        )

    def _contacto(self, numero_identificacion):
        """El tenant de pruebas no carga fixtures: la cadena ciudad -> estado -> país va acá."""
        pais, _ = GenPais.objects.get_or_create(id=250, nombre='Colombia', codigo='CO')
        estado, _ = GenEstado.objects.get_or_create(
            id=1, nombre='Antioquia', codigo='05', pais=pais,
        )
        ciudad, _ = GenCiudad.objects.get_or_create(
            id=1, nombre='Medellín', codigo='05001', estado=estado,
        )
        identificacion, _ = GenIdentificacion.objects.get_or_create(
            id=6, nombre='Número de identificación tributaria', codigo='31',
        )
        tipo_persona, _ = GenTipoPersona.objects.get_or_create(id=1, nombre='Jurídica')
        return GenContacto.objects.create(
            numero_identificacion=numero_identificacion,
            nombre_corto=f'Contacto {numero_identificacion}',
            ciudad=ciudad, identificacion=identificacion, tipo_persona=tipo_persona,
            direccion='calle 1', telefono='1', correo='t@t.com',
        )

    def _movimiento(self, cuenta, fecha, debito=0, credito=0, centro_costo=None, contacto=None,
                    base=0, detalle=None, cierre=False):
        return ConMovimiento.objects.create(
            fecha=fecha,
            cierre=cierre,
            debito=Decimal(debito),
            credito=Decimal(credito),
            base=Decimal(base),
            detalle=detalle,
            naturaleza='D' if debito else 'C',
            comprobante=self.comprobante,
            periodo=self.anterior if fecha.year == 2025 else self.periodo,
            cuenta=cuenta,
            centro_costo=centro_costo,
            contacto=contacto,
        )

    def _post(self, accion, **payload):
        payload.setdefault('informe', self.informe)
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

    def _auxiliares(self, **payload):
        return [fila for fila in self._lista(**payload) if fila['tipo'] == 'AUXILIAR']

    def _jerarquia(self, **payload):
        """Las filas del balance, sin el detalle que agregan los auxiliares."""
        return [
            fila for fila in self._lista(**payload)
            if fila['tipo'] not in ('TERCERO', 'MOVIMIENTO')
        ]

    def _totales(self, **payload):
        response = self._post('totales', **payload)
        self.assertEqual(response.status_code, 200)
        return {clave: Decimal(valor) for clave, valor in response.data.items()}

    def _fila(self, filas, codigo):
        return next(fila for fila in filas if fila['codigo'] == codigo)


class BalancePruebaTests(_InformeBase):
    """
    El balance recorre el plan de cuentas y le pega el movimiento de un rango:
    lo anterior al corte llega neteado como saldo anterior y lo que cae dentro
    como débito y crédito del periodo. Ningún saldo está guardado —todo sale de
    sumar `con_movimiento`—, así que estas pruebas son la única red que detecta
    un corte mal puesto o un subtotal que no cuadra con sus hojas.
    """

    informe = 'balance_prueba'
    archivo_excel = 'balance_prueba.xlsx'
    titulo_excel = 'Balance de prueba'
    encabezados_excel = [
        'Tipo', 'Cuenta', 'Nombre de cuenta',
        'Saldo anterior ($)', 'Debitos ($)', 'Creditos ($)', 'Saldo actual ($)',
    ]

    def test_lo_anterior_al_rango_llega_como_saldo_anterior(self):
        self._movimiento(self.caja, date(2025, 12, 31), debito=100)
        self._movimiento(self.caja, date(2026, 1, 15), debito=40)

        fila = self._fila(self._auxiliares(), '11050505')

        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(100))
        self.assertEqual(Decimal(fila['debito']), Decimal(40))
        self.assertEqual(Decimal(fila['credito']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(140))

    def test_la_cuenta_sin_movimiento_en_el_rango_aparece_con_su_saldo(self):
        """
        Es la mitad del balance que se pierde si el saldo anterior se calcula
        sobre las cuentas que movieron en el rango: la cuenta quieta también
        tiene saldo y tiene que sumar al cuadre.
        """
        self._movimiento(self.banco, date(2025, 6, 30), debito=70)

        fila = self._fila(self._auxiliares(), '11100505')

        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(70))
        self.assertEqual(Decimal(fila['debito']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(70))

    def test_la_cuenta_que_nunca_movio_sale_en_ceros(self):
        """
        El recorrido lo manda el plan de cuentas, no los movimientos: el informe
        se lee contra el plan completo, y una cuenta sin un solo movimiento en su
        historia también es una fila del balance.
        """
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)

        fila = self._fila(self._auxiliares(), '11100505')

        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(0))
        self.assertEqual(Decimal(fila['debito']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(0))

    def test_lo_posterior_al_rango_no_entra(self):
        self._movimiento(self.caja, date(2026, 1, 10), debito=30)
        self._movimiento(self.caja, date(2026, 2, 5), debito=999)

        fila = self._fila(self._auxiliares(), '11050505')

        self.assertEqual(Decimal(fila['debito']), Decimal(30))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(30))

    def test_el_saldo_neto_acreedor_sale_negativo(self):
        """
        El saldo va con signo en una sola columna, no partido en débito y
        crédito: es lo que deja sumar los subtotales sin volver a interpretarlo.
        """
        self._movimiento(self.caja, date(2025, 12, 1), credito=80)
        self._movimiento(self.caja, date(2026, 1, 20), credito=20)

        fila = self._fila(self._auxiliares(), '11050505')

        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(-80))
        self.assertEqual(Decimal(fila['credito']), Decimal(20))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(-100))

    def test_una_fila_por_cuenta(self):
        """
        `ConMovimiento.Meta.ordering` es `['-id']`, y sobre un queryset agrupado
        Django mete el campo de ordenamiento en el GROUP BY: sin vaciarlo en el
        servicio, la cuenta llegaría partida en tres agregados.
        """
        for dia in (5, 10, 15):
            self._movimiento(self.caja, date(2026, 1, dia), debito=10)

        filas = [f for f in self._auxiliares() if f['codigo'] == '11050505']

        self.assertEqual(len(filas), 1)
        self.assertEqual(Decimal(filas[0]['debito']), Decimal(30))

    def test_cada_auxiliar_viene_precedido_por_su_jerarquia(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=10)

        filas = self._jerarquia()

        self.assertEqual(
            [(fila['tipo'], fila['codigo']) for fila in filas],
            [
                ('CLASE', '1'),
                ('GRUPO', '11'),
                ('CUENTA', '1105'),
                ('AUXILIAR', '11050505'),
                ('CUENTA', '1110'),
                ('AUXILIAR', '11100505'),
            ],
        )

    def test_el_subtotal_suma_sus_hojas(self):
        self._movimiento(self.caja, date(2025, 12, 1), debito=100)
        self._movimiento(self.caja, date(2026, 1, 5), debito=30)
        self._movimiento(self.banco, date(2026, 1, 5), credito=12)

        filas = self._jerarquia()
        clase = self._fila(filas, '1')
        grupo = self._fila(filas, '11')

        self.assertEqual(Decimal(clase['saldo_anterior']), Decimal(100))
        self.assertEqual(Decimal(clase['debito']), Decimal(30))
        self.assertEqual(Decimal(clase['credito']), Decimal(12))
        self.assertEqual(Decimal(clase['saldo_final']), Decimal(118))
        self.assertEqual(clase['cuenta_id'], None)
        self.assertEqual(
            [Decimal(grupo[columna]) for columna in ('saldo_anterior', 'debito', 'credito')],
            [Decimal(100), Decimal(30), Decimal(12)],
        )

    def test_el_subtotal_de_cuenta_no_arrastra_al_de_la_cuenta_siguiente(self):
        """
        Los subtotales se emiten por cambio de nivel sobre las hojas ordenadas.
        Si el acumulado no se llevara por cuenta sino corrido, el subtotal de
        `1110` traería adentro lo de `1105`.
        """
        self._movimiento(self.caja, date(2026, 1, 5), debito=40)
        self._movimiento(self.banco, date(2026, 1, 5), debito=7)

        filas = self._jerarquia()

        self.assertEqual(Decimal(self._fila(filas, '1105')['debito']), Decimal(40))
        self.assertEqual(Decimal(self._fila(filas, '1110')['debito']), Decimal(7))

    def test_los_totales_cuadran(self):
        self._movimiento(self.caja, date(2025, 12, 31), debito=200)
        self._movimiento(self.banco, date(2025, 12, 31), credito=200)
        self._movimiento(self.caja, date(2026, 1, 15), debito=50)
        self._movimiento(self.banco, date(2026, 1, 15), credito=50)

        totales = self._totales()

        self.assertEqual(totales['saldo_anterior'], Decimal(0))
        self.assertEqual(totales['saldo_final'], Decimal(0))
        self.assertEqual(totales['debito'], totales['credito'])
        self.assertEqual(totales['debito'], Decimal(50))

    def test_los_totales_no_cuentan_los_subtotales(self):
        """
        Cada importe está en su hoja y otra vez en las tres filas de subtotal que
        cuelgan de ella. Sumar el informe entero lo contaría cuatro veces.
        """
        self._movimiento(self.caja, date(2026, 1, 15), debito=50)

        self.assertEqual(self._totales()['debito'], Decimal(50))

    def test_el_asiento_de_cierre_no_es_movimiento_del_periodo(self):
        """
        El cierre cancela las cuentas de resultado contra el ejercicio. Si contara
        como movimiento del rango, la columna de débito de diciembre traería el
        resultado del año entero además de lo que se movió en el mes.
        """
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)
        self._movimiento(self.caja, date(2026, 1, 31), credito=25, cierre=True)

        fila = self._fila(self._auxiliares(), '11050505')

        self.assertEqual(Decimal(fila['debito']), Decimal(25))
        self.assertEqual(Decimal(fila['credito']), Decimal(0))

    def test_el_asiento_de_cierre_anterior_si_cuenta_en_el_saldo(self):
        """
        La otra mitad de la regla: el saldo con el que la cuenta llega al rango es
        el que quedó *después* del cierre. Excluirlo de las dos mitades dejaría el
        saldo anterior con el resultado del año anterior sin cancelar.
        """
        self._movimiento(self.caja, date(2025, 12, 1), debito=100)
        self._movimiento(self.caja, date(2025, 12, 31), credito=40, cierre=True)

        fila = self._fila(self._auxiliares(), '11050505')

        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(60))

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
        fila = self._fila(filas, '11050505')

        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(100))
        self.assertEqual(Decimal(fila['debito']), Decimal(10))

    def test_las_cuentas_salen_por_codigo(self):
        self._movimiento(self.banco, date(2026, 1, 5), debito=10)
        self._movimiento(self.caja, date(2026, 1, 5), debito=10)

        self.assertEqual(
            [fila['codigo'] for fila in self._auxiliares()], ['11050505', '11100505'],
        )

    def test_con_solo_con_saldo_se_omite_la_cuenta_en_ceros(self):
        """
        La cuenta movió alguna vez, se canceló y no volvió a moverse: llega al
        rango con saldo cero y sin movimiento, así que es una fila de puros ceros
        que solo estorba en el balance.
        """
        self._movimiento(self.banco, date(2025, 3, 1), debito=90)
        self._movimiento(self.banco, date(2025, 4, 1), credito=90)
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)

        codigos = [fila['codigo'] for fila in self._auxiliares(solo_con_saldo=True)]

        self.assertEqual(codigos, ['11050505'])

    def test_el_subtotal_sin_hojas_no_se_emite(self):
        """Podadas sus cuentas, el subtotal de la cuenta contable no tiene qué decir."""
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)

        codigos = [fila['codigo'] for fila in self._jerarquia(solo_con_saldo=True)]

        self.assertEqual(codigos, ['1', '11', '1105', '11050505'])

    def test_la_cuenta_que_movio_en_el_rango_y_quedo_en_cero_si_sale(self):
        """
        Netea cero pero movió dentro del rango: el débito y el crédito del periodo
        son parte del balance aunque el saldo final quede en cero.
        """
        self._movimiento(self.banco, date(2026, 1, 5), debito=60)
        self._movimiento(self.banco, date(2026, 1, 20), credito=60)

        fila = self._fila(self._auxiliares(solo_con_saldo=True), '11100505')

        self.assertEqual(Decimal(fila['debito']), Decimal(60))
        self.assertEqual(Decimal(fila['credito']), Decimal(60))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(0))

    def test_omitir_ceros_no_cambia_los_totales(self):
        """Una fila en ceros aporta cero a las cuatro columnas, con o sin la bandera."""
        self._movimiento(self.banco, date(2025, 3, 1), debito=90)
        self._movimiento(self.banco, date(2025, 4, 1), credito=90)
        self._movimiento(self.caja, date(2026, 1, 10), debito=25)

        self.assertEqual(self._totales(), self._totales(solo_con_saldo=True))

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

    def test_el_excel_trae_el_encabezado_y_las_filas_del_informe(self):
        GenConfiguracion.objects.update_or_create(
            id=1, defaults={'gen_empresa_razon_social': 'Semantica Digital S.A.S'},
        )
        self._movimiento(self.caja, date(2026, 1, 5), debito=10)

        response = self._post('excel')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn(self.archivo_excel, response['Content-Disposition'])

        hoja = load_workbook(BytesIO(response.content)).active
        self.assertEqual(hoja['A1'].value, self.titulo_excel)
        self.assertEqual(hoja['A2'].value, 'Semantica Digital S.A.S')
        self.assertEqual(hoja['A4'].value, 'Fecha desde: 2026-01-01')
        self.assertEqual(hoja['A5'].value, 'Fecha hasta: 2026-01-31')
        self.assertEqual([celda.value for celda in hoja[7]], self.encabezados_excel)
        self.assertEqual([celda.value for celda in hoja[8]][:3], ['CLASE', '1', 'Activo'])
        self.assertEqual(hoja.cell(row=11, column=1).value, 'AUXILIAR')


class BalancePruebaContactoTests(BalancePruebaTests):
    """
    El balance por contacto es el mismo informe con las cuentas abiertas por
    tercero, así que hereda entera la batería del balance: el auxiliar tiene que
    seguir siendo el total de la cuenta y los subtotales tienen que seguir
    saliendo de los auxiliares, esté o no el detalle debajo. Lo que se agrega acá
    es lo que el detalle trae de nuevo.
    """

    informe = 'balance_prueba_contacto'
    archivo_excel = 'balance_prueba_contacto.xlsx'
    titulo_excel = 'Balance de prueba por contacto'
    encabezados_excel = [
        'Tipo', 'Cuenta', 'Nombre Cuenta', 'Identificación', 'Contacto',
        'Saldo anterior ($)', 'Debitos ($)', 'Creditos ($)', 'Saldo actual ($)',
    ]

    def setUp(self):
        super().setUp()
        self.uno = self._contacto('900000001')
        self.dos = self._contacto('900000002')

    def _terceros(self, filas, codigo):
        return [
            fila for fila in filas
            if fila['tipo'] == 'TERCERO' and fila['codigo'] == codigo
        ]

    def test_el_detalle_cuelga_del_auxiliar_ordenado_por_contacto(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.dos)
        self._movimiento(self.caja, date(2026, 1, 6), debito=10, contacto=self.uno)

        filas = [fila for fila in self._lista() if fila['tipo'] != 'MOVIMIENTO']
        posicion = [fila['tipo'] for fila in filas].index('AUXILIAR')

        self.assertEqual(
            [(fila['tipo'], fila['identificacion']) for fila in filas[posicion:posicion + 3]],
            [('AUXILIAR', None), ('TERCERO', '900000001'), ('TERCERO', '900000002')],
        )

    def test_el_detalle_suma_su_auxiliar(self):
        self._movimiento(self.caja, date(2025, 12, 1), debito=100, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 5), credito=12, contacto=self.dos)

        filas = self._lista()
        auxiliar = self._fila(self._auxiliares(), '11050505')
        terceros = self._terceros(filas, '11050505')

        self.assertEqual(
            [Decimal(auxiliar[columna]) for columna in ('saldo_anterior', 'debito', 'credito')],
            [Decimal(100), Decimal(30), Decimal(12)],
        )
        for columna in ('saldo_anterior', 'debito', 'credito', 'saldo_final'):
            self.assertEqual(
                sum(Decimal(tercero[columna]) for tercero in terceros),
                Decimal(auxiliar[columna]),
                columna,
            )

    def test_el_tercero_que_no_movio_en_el_rango_sale_con_su_saldo(self):
        """
        El detalle se lee contra los contactos que movieron la cuenta alguna vez,
        no contra los del rango: si no, el saldo anterior de la cuenta quedaría
        repartido entre menos terceros de los que lo formaron.
        """
        self._movimiento(self.caja, date(2025, 12, 1), debito=100, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.dos)

        tercero = self._fila(self._terceros(self._lista(), '11050505'), '11050505')

        self.assertEqual(tercero['identificacion'], '900000001')
        self.assertEqual(Decimal(tercero['saldo_anterior']), Decimal(100))
        self.assertEqual(Decimal(tercero['debito']), Decimal(0))
        self.assertEqual(Decimal(tercero['saldo_final']), Decimal(100))

    def test_el_movimiento_sin_contacto_entra_al_auxiliar_pero_no_al_detalle(self):
        """
        Que una cuenta mezcle movimientos con y sin tercero es un error de datos.
        Cuando pasa, el auxiliar sigue siendo el total de la cuenta —el informe no
        pierde plata— y el detalle solo muestra lo que tiene tercero.
        """
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), debito=70)

        filas = self._lista()
        auxiliar = self._fila(self._auxiliares(), '11050505')
        terceros = self._terceros(filas, '11050505')

        self.assertEqual(Decimal(auxiliar['debito']), Decimal(100))
        self.assertEqual([Decimal(t['debito']) for t in terceros], [Decimal(30)])

    def test_el_detalle_no_entra_en_los_subtotales_ni_en_los_totales(self):
        """
        Cada importe está en su tercero, en su auxiliar y en las tres filas de
        subtotal. Contarlos todos multiplicaría el balance por cinco.
        """
        self._movimiento(self.caja, date(2026, 1, 5), debito=50, contacto=self.uno)

        self.assertEqual(Decimal(self._fila(self._lista(), '1')['debito']), Decimal(50))
        self.assertEqual(self._totales()['debito'], Decimal(50))

    def test_las_columnas_de_contacto_van_vacias_fuera_del_detalle(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=50, contacto=self.uno)

        for fila in self._lista():
            if fila['tipo'] in ('TERCERO', 'MOVIMIENTO'):
                continue
            self.assertEqual(
                (fila['contacto_id'], fila['identificacion'], fila['contacto']),
                (None, None, None),
                fila['codigo'],
            )

    def test_con_solo_con_saldo_se_poda_el_tercero_en_ceros(self):
        self._movimiento(self.caja, date(2025, 3, 1), debito=90, contacto=self.uno)
        self._movimiento(self.caja, date(2025, 4, 1), credito=90, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 5), debito=50, contacto=self.dos)

        terceros = self._terceros(self._lista(solo_con_saldo=True), '11050505')

        self.assertEqual([t['identificacion'] for t in terceros], ['900000002'])

    def test_el_excel_trae_la_fila_del_tercero(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=10, contacto=self.uno)

        response = self._post('excel')
        hoja = load_workbook(BytesIO(response.content)).active

        debito = self.encabezados_excel.index('Debitos ($)') + 1

        self.assertEqual(
            [celda.value for celda in hoja[12]][:5],
            ['TERCERO', '11050505', 'Cuenta 11050505', '900000001', 'Contacto 900000001'],
        )
        self.assertEqual(hoja.cell(row=12, column=debito).value, 10)

class _AuxiliarMixin:
    """Helpers comunes a los tres auxiliares."""

    def _movimientos(self, filas, codigo=None):
        return [
            fila for fila in filas
            if fila['tipo'] == 'MOVIMIENTO' and (codigo is None or fila['codigo'] == codigo)
        ]

    def test_el_movimiento_no_lleva_saldo(self):
        """
        Un movimiento no tiene saldo, tiene débito o crédito. Si trajera el neto
        del asiento —o peor, un acumulado corrido— dejaría de cuadrar con el
        auxiliar de arriba.
        """
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.contacto)

        fila = self._movimientos(self._lista())[0]

        self.assertEqual(Decimal(fila['saldo_anterior']), Decimal(0))
        self.assertEqual(Decimal(fila['saldo_final']), Decimal(0))
        self.assertEqual(Decimal(fila['debito']), Decimal(30))

    def test_el_movimiento_anterior_al_rango_no_baja_al_detalle(self):
        """
        El saldo anterior es un acumulado, no una lista: entra al auxiliar y al
        tercero, nunca al detalle. Si bajara, el auxiliar mostraría movimientos
        que no explican su columna de débito.
        """
        self._movimiento(self.caja, date(2025, 12, 1), debito=100, contacto=self.contacto)
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.contacto)

        filas = self._lista()

        auxiliar = self._fila(self._auxiliares(), '11050505')

        self.assertEqual(Decimal(auxiliar['saldo_anterior']), Decimal(100))
        self.assertEqual(
            [Decimal(fila['debito']) for fila in self._movimientos(filas, '11050505')],
            [Decimal(30)],
        )

    def test_los_movimientos_salen_por_fecha_y_numero(self):
        """
        Cronológico y, dentro del día, por número de asiento. El importe hace de
        etiqueta porque el número solo lo expone `auxiliar_general`.
        """
        asientos = (
            (date(2026, 1, 20), 1, 3),
            (date(2026, 1, 5), 9, 2),
            (date(2026, 1, 5), 2, 1),
        )
        for fecha, numero, debito in asientos:
            movimiento = self._movimiento(self.caja, fecha, debito=debito, contacto=self.contacto)
            ConMovimiento.objects.filter(id=movimiento.id).update(numero=numero)

        filas = self._movimientos(self._lista(), '11050505')

        self.assertEqual(
            [Decimal(fila['debito']) for fila in filas], [Decimal(1), Decimal(2), Decimal(3)],
        )

    def test_el_asiento_de_cierre_no_baja_al_detalle(self):
        """
        El detalle explica las columnas de débito y crédito del auxiliar, y el
        cierre no está en ellas: si bajara, el auxiliar no cuadraría con su lista.
        """
        self._movimiento(self.caja, date(2026, 1, 10), debito=25, contacto=self.contacto)
        self._movimiento(self.caja, date(2026, 1, 31), credito=25, cierre=True,
                         contacto=self.contacto)

        filas = self._movimientos(self._lista(), '11050505')

        self.assertEqual([Decimal(fila['debito']) for fila in filas], [Decimal(25)])

    def test_el_detalle_no_entra_en_los_totales(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=50, contacto=self.contacto)

        self.assertEqual(self._totales()['debito'], Decimal(50))
        self.assertEqual(Decimal(self._fila(self._jerarquia(), '1')['debito']), Decimal(50))


class AuxiliarCuentaTests(_AuxiliarMixin, BalancePruebaTests):
    """
    El auxiliar por cuenta es el balance con los asientos del rango debajo de
    cada auxiliar, así que hereda entera la batería del balance: agregarle el
    detalle no puede haber movido un solo importe de la mitad de arriba.
    """

    informe = 'auxiliar_cuenta'
    archivo_excel = 'auxiliar_cuenta.xlsx'
    titulo_excel = 'Auxiliar cuenta'

    def setUp(self):
        super().setUp()
        self.contacto = None

    def test_el_movimiento_cuelga_de_su_auxiliar(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=30)
        self._movimiento(self.banco, date(2026, 1, 6), credito=7)

        filas = self._lista()

        self.assertEqual(
            [(fila['tipo'], fila['codigo']) for fila in filas],
            [
                ('CLASE', '1'),
                ('GRUPO', '11'),
                ('CUENTA', '1105'),
                ('AUXILIAR', '11050505'),
                ('MOVIMIENTO', '11050505'),
                ('CUENTA', '1110'),
                ('AUXILIAR', '11100505'),
                ('MOVIMIENTO', '11100505'),
            ],
        )

    def test_el_movimiento_fuera_del_rango_no_baja_al_detalle(self):
        self._movimiento(self.caja, date(2026, 1, 10), debito=30)
        self._movimiento(self.caja, date(2026, 2, 5), debito=999)

        self.assertEqual(
            [Decimal(fila['debito']) for fila in self._movimientos(self._lista())],
            [Decimal(30)],
        )

    # ------------------------------------------------------------- filtros ----

    def test_filtra_por_numero(self):
        """El auxiliar general identifica cada asiento, así que se puede acotar a uno."""
        uno = self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        dos = self._movimiento(self.caja, date(2026, 1, 6), debito=70, contacto=self.uno)
        ConMovimiento.objects.filter(id=uno.id).update(numero=77)
        ConMovimiento.objects.filter(id=dos.id).update(numero=88)

        filas = self._lista(filtros=[
            {'propiedad': 'numero', 'operador': '=', 'valor': 77},
        ])

        self.assertEqual([f['numero'] for f in self._movimientos(filas)], [77])
        self.assertEqual(Decimal(self._fila(self._auxiliares(filtros=[
            {'propiedad': 'numero', 'operador': '=', 'valor': 77},
        ]), '11050505')['debito']), Decimal(30))

    def test_filtra_por_contacto(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), debito=70, contacto=self.dos)

        filas = self._lista(filtros=[
            {'propiedad': 'contacto_id', 'operador': '=', 'valor': self.uno.id},
        ])

        self.assertEqual(
            [f['identificacion'] for f in self._movimientos(filas)], ['900000001'],
        )
        self.assertEqual(Decimal(self._fila(self._auxiliares(filtros=[
            {'propiedad': 'contacto_id', 'operador': '=', 'valor': self.uno.id},
        ]), '11050505')['debito']), Decimal(30))

    def test_filtra_por_comprobante(self):
        otro = ConComprobante.objects.create(id=2, nombre='Otro comprobante')
        uno = self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        dos = self._movimiento(self.caja, date(2026, 1, 6), debito=70, contacto=self.uno)
        ConMovimiento.objects.filter(id=dos.id).update(comprobante=otro)

        filas = self._lista(filtros=[
            {'propiedad': 'comprobante_id', 'operador': '=', 'valor': otro.id},
        ])
        movimientos = self._movimientos(filas)

        self.assertEqual([f['comprobante'] for f in movimientos], ['Otro comprobante'])
        self.assertEqual([f['movimiento_id'] for f in movimientos], [dos.id])
        self.assertNotIn(uno.id, [f['movimiento_id'] for f in movimientos])

    def test_el_movimiento_sin_contacto_baja_igual(self):
        """El informe es por cuenta: que el asiento no tenga tercero no lo excluye."""
        self._movimiento(self.caja, date(2026, 1, 5), debito=30)

        self.assertEqual(len(self._movimientos(self._lista())), 1)


class AuxiliarContactoTests(_AuxiliarMixin, BalancePruebaContactoTests):
    """El auxiliar por contacto: cada tercero seguido de sus propios asientos."""

    informe = 'auxiliar_contacto'
    archivo_excel = 'auxiliar_contacto.xlsx'
    titulo_excel = 'Auxiliar por contacto'

    def setUp(self):
        super().setUp()
        self.contacto = self.uno

    def test_cada_movimiento_va_bajo_su_tercero(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.dos)
        self._movimiento(self.caja, date(2026, 1, 6), debito=10, contacto=self.uno)

        filas = self._lista()
        posicion = [fila['tipo'] for fila in filas].index('AUXILIAR')

        self.assertEqual(
            [(fila['tipo'], fila['identificacion']) for fila in filas[posicion:posicion + 5]],
            [
                ('AUXILIAR', None),
                ('TERCERO', '900000001'),
                ('MOVIMIENTO', '900000001'),
                ('TERCERO', '900000002'),
                ('MOVIMIENTO', '900000002'),
            ],
        )

    def test_el_movimiento_sin_contacto_no_baja_al_detalle(self):
        """
        No cuelga de ningún tercero, y este informe es por tercero. El importe no
        se pierde: sigue dentro del total del auxiliar.
        """
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), debito=70)

        filas = self._lista()
        auxiliar = self._fila(self._auxiliares(), '11050505')

        self.assertEqual(Decimal(auxiliar['debito']), Decimal(100))
        self.assertEqual(
            [Decimal(fila['debito']) for fila in self._movimientos(filas, '11050505')],
            [Decimal(30)],
        )


class AuxiliarGeneralTests(_AuxiliarMixin, BalancePruebaContactoTests):
    """El auxiliar general: los terceros de la cuenta y después todos sus asientos."""

    informe = 'auxiliar_general'
    archivo_excel = 'auxiliar_general.xlsx'
    titulo_excel = 'Auxiliar general'
    encabezados_excel = [
        'Tipo', 'Cuenta', 'Nombre Cuenta', 'Identificación', 'Contacto',
        'Comprobante', 'Numero', 'Fecha',
        'Saldo anterior ($)', 'Debitos ($)', 'Creditos ($)', 'Saldo actual ($)',
    ]

    def setUp(self):
        super().setUp()
        self.contacto = self.uno

    def test_los_movimientos_van_despues_de_todos_los_terceros(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.dos)
        self._movimiento(self.caja, date(2026, 1, 6), debito=10, contacto=self.uno)

        filas = self._lista()
        posicion = [fila['tipo'] for fila in filas].index('AUXILIAR')

        self.assertEqual(
            [(fila['tipo'], fila['identificacion']) for fila in filas[posicion:posicion + 5]],
            [
                ('AUXILIAR', None),
                ('TERCERO', '900000001'),
                ('TERCERO', '900000002'),
                ('MOVIMIENTO', '900000002'),
                ('MOVIMIENTO', '900000001'),
            ],
        )

    def test_el_movimiento_trae_su_asiento(self):
        movimiento = self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        ConMovimiento.objects.filter(id=movimiento.id).update(numero=77)

        fila = self._movimientos(self._lista())[0]

        self.assertEqual(fila['comprobante'], 'Comprobante')
        self.assertEqual(fila['numero'], 77)
        self.assertEqual(fila['fecha'], '2026-01-05')
        self.assertEqual(fila['movimiento_id'], movimiento.id)

    def test_el_movimiento_sin_contacto_baja_igual(self):
        """A diferencia del auxiliar por contacto, acá el detalle es de la cuenta entera."""
        self._movimiento(self.caja, date(2026, 1, 5), debito=30, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), debito=70)

        filas = self._movimientos(self._lista(), '11050505')

        self.assertEqual([fila['identificacion'] for fila in filas], ['900000001', None])



class _InformePlanoMixin:
    """
    Lo común a los cuatro informes planos: no recorren el plan de cuentas sino lo
    que pasó en el rango, así que no tienen jerarquía ni subtotales que probar.
    """

    def test_el_excel_trae_el_encabezado_y_las_columnas_del_informe(self):
        GenConfiguracion.objects.update_or_create(
            id=1, defaults={'gen_empresa_razon_social': 'Semantica Digital S.A.S'},
        )
        self._poblar()

        response = self._post('excel')

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.archivo_excel, response['Content-Disposition'])

        hoja = load_workbook(BytesIO(response.content)).active
        self.assertEqual(hoja['A1'].value, self.titulo_excel)
        self.assertEqual(hoja['A2'].value, 'Semantica Digital S.A.S')
        self.assertEqual(hoja['A4'].value, 'Fecha desde: 2026-01-01')
        self.assertEqual([celda.value for celda in hoja[7]], self.encabezados_excel)

    def test_no_hay_jerarquia_que_armar(self):
        """
        Un informe plano no tiene subtotales: si los tuviera, `totales/` los
        contaría dos veces, porque suma todas sus filas sin descontar nada.
        """
        self._poblar()

        tipos = {fila['tipo'] for fila in self._lista()}

        self.assertNotIn('CLASE', tipos)
        self.assertNotIn('AUXILIAR', tipos)


class BasesTests(_InformePlanoMixin, _InformeBase):
    """
    El informe de bases lista los asientos de las cuentas que exigen base. Lo que
    decide qué entra es la cuenta, no el importe: es la única forma de ver que a
    un asiento le falta la base.
    """

    informe = 'bases'
    archivo_excel = 'bases.xlsx'
    titulo_excel = 'Informe de bases'
    encabezados_excel = [
        'Cuenta', 'Nombre Cuenta', 'Identificación', 'Contacto', 'Comprobante',
        'Numero', 'Fecha', 'Detalle', 'Debitos ($)', 'Creditos ($)', 'Base ($)',
    ]

    def setUp(self):
        super().setUp()
        self.retencion = self._cuenta('13551505', self.grupo_caja, exige_base=True)
        self.uno = self._contacto('900000001')

    def _poblar(self):
        self._movimiento(
            self.retencion, date(2026, 1, 5), debito=40, base=1000,
            contacto=self.uno, detalle='IMPUESTO',
        )

    def test_solo_entran_las_cuentas_que_exigen_base(self):
        self._poblar()
        self._movimiento(self.caja, date(2026, 1, 5), debito=99, base=5000)

        self.assertEqual([fila['codigo'] for fila in self._lista()], ['13551505'])

    def test_el_asiento_sin_base_sale_en_cero(self):
        """
        Es el punto del informe: la cuenta exige base y el asiento no la trae, así
        que tiene que verse. Filtrar por `base != 0` lo escondería.
        """
        self._movimiento(self.retencion, date(2026, 1, 5), debito=40, contacto=self.uno)

        fila = self._lista()[0]

        self.assertEqual(Decimal(fila['base']), Decimal(0))
        self.assertEqual(Decimal(fila['debito']), Decimal(40))

    def test_la_fila_trae_el_asiento_completo(self):
        self._poblar()

        fila = self._lista()[0]

        self.assertEqual(fila['nombre'], 'Cuenta 13551505')
        self.assertEqual(fila['identificacion'], '900000001')
        self.assertEqual(fila['comprobante'], 'Comprobante')
        self.assertEqual(fila['fecha'], '2026-01-05')
        self.assertEqual(fila['detalle'], 'IMPUESTO')
        self.assertEqual(Decimal(fila['base']), Decimal(1000))

    def test_lo_de_fuera_del_rango_no_entra(self):
        self._poblar()
        self._movimiento(self.retencion, date(2026, 2, 5), debito=99, base=9999)

        self.assertEqual([Decimal(f['base']) for f in self._lista()], [Decimal(1000)])

    def test_las_filas_salen_por_cuenta_fecha_y_numero(self):
        otra = self._cuenta('13551510', self.grupo_caja, exige_base=True)
        asientos = (
            (otra, date(2026, 1, 5), 1, 4),
            (self.retencion, date(2026, 1, 20), 1, 3),
            (self.retencion, date(2026, 1, 5), 9, 2),
            (self.retencion, date(2026, 1, 5), 2, 1),
        )
        for cuenta, fecha, numero, base in asientos:
            movimiento = self._movimiento(cuenta, fecha, debito=1, base=base)
            ConMovimiento.objects.filter(id=movimiento.id).update(numero=numero)

        self.assertEqual(
            [Decimal(fila['base']) for fila in self._lista()],
            [Decimal(1), Decimal(2), Decimal(3), Decimal(4)],
        )

    def test_el_asiento_de_cierre_entra_igual(self):
        """
        Los informes planos no son un corte del periodo sino la lista de lo que
        pasó, así que acá el cierre no se descuenta.
        """
        self._poblar()
        self._movimiento(self.retencion, date(2026, 1, 31), credito=40, base=1000, cierre=True)

        self.assertEqual(len(self._lista()), 2)

    def test_los_totales_suman_las_tres_columnas(self):
        self._poblar()
        self._movimiento(self.retencion, date(2026, 1, 6), credito=15, base=500)

        totales = self._totales()

        self.assertEqual(totales['debito'], Decimal(40))
        self.assertEqual(totales['credito'], Decimal(15))
        self.assertEqual(totales['base'], Decimal(1500))


class CertificadoRetencionTests(_InformePlanoMixin, _InformeBase):
    """
    El certificado agrupa por cuenta y tercero lo retenido y la base que lo
    causó. No filtra por cuenta: quien lo emite acota con los filtros del
    informe, igual que hacía itrio con su rango de códigos.
    """

    informe = 'certificado_retencion'
    archivo_excel = 'certificado_retencion.xlsx'
    titulo_excel = 'Certificado retenciones'
    encabezados_excel = [
        'Identificación', 'Contacto', 'Cuenta', 'Nombre cuenta',
        'Monto del pago sujeto a retención ($)', 'Retenido y consignado ($)',
    ]

    def setUp(self):
        super().setUp()
        self.uno = self._contacto('900000001')
        self.dos = self._contacto('900000002')

    def _poblar(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=40, base=1000, contacto=self.uno)

    def test_agrupa_por_cuenta_y_tercero(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=40, base=1000, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), debito=20, base=500, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), debito=8, base=200, contacto=self.dos)

        filas = self._lista()

        self.assertEqual([fila['identificacion'] for fila in filas], ['900000001', '900000002'])
        self.assertEqual(Decimal(filas[0]['retenido']), Decimal(60))
        self.assertEqual(Decimal(filas[0]['base_retenido']), Decimal(1500))

    def test_el_credito_resta_su_base(self):
        """
        La base siempre es positiva: lo que dice si suma o resta es el signo del
        movimiento. Un reverso de retención tiene que descontar su base, no
        sumarla.
        """
        self._movimiento(self.caja, date(2026, 1, 5), debito=40, base=1000, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), credito=12, base=300, contacto=self.uno)

        fila = self._lista()[0]

        self.assertEqual(Decimal(fila['retenido']), Decimal(28))
        self.assertEqual(Decimal(fila['base_retenido']), Decimal(700))

    def test_los_totales_suman_lo_retenido(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=40, base=1000, contacto=self.uno)
        self._movimiento(self.caja, date(2026, 1, 6), debito=8, base=200, contacto=self.dos)

        totales = self._totales()

        self.assertEqual(totales['retenido'], Decimal(48))
        self.assertEqual(totales['base_retenido'], Decimal(1200))


class EstadoResultadosTests(_InformePlanoMixin, _InformeBase):
    """
    El estado de resultados es el movimiento del periodo de las cuentas de
    resultado, con el saldo invertido para que el ingreso se lea positivo.
    """

    informe = 'estado_resultados'
    archivo_excel = 'estado_resultados.xlsx'
    titulo_excel = 'Estado de resultados'
    encabezados_excel = ['Clase', 'Grupo', 'Codigo cuenta', 'Nombre cuenta', 'Saldo ($)']

    def setUp(self):
        super().setUp()
        self.clase_ingreso = ConCuentaClase.objects.create(id=4, nombre='Ingresos')
        self.grupo_ingreso = ConCuentaGrupo.objects.create(id=41, nombre='Operacionales')
        self.cuenta_ingreso = ConCuentaCuenta.objects.create(id=4135, nombre='Comercio')
        self.venta = self._cuenta(
            '41350505', self.cuenta_ingreso,
            cuenta_clase=self.clase_ingreso, cuenta_grupo=self.grupo_ingreso,
        )

    def _poblar(self):
        self._movimiento(self.venta, date(2026, 1, 5), credito=100)

    def test_el_ingreso_se_lee_positivo(self):
        """
        El saldo va `crédito − débito`, al revés que en el balance. Las dos cosas
        son correctas: son convenciones de presentación distintas del mismo neto.
        """
        self._poblar()

        fila = self._lista()[0]

        self.assertEqual(Decimal(fila['saldo']), Decimal(100))
        self.assertEqual(fila['clase'], 'Ingresos')
        self.assertEqual(fila['grupo'], 'Operacionales')

    def test_las_cuentas_de_balance_no_entran(self):
        self._poblar()
        self._movimiento(self.caja, date(2026, 1, 5), debito=100)

        self.assertEqual([fila['codigo'] for fila in self._lista()], ['41350505'])

    def test_la_cuenta_que_no_movio_no_es_una_linea(self):
        """
        A diferencia del balance, este informe no se lee contra el plan: una
        cuenta de resultado sin movimiento en el periodo no tiene nada que decir.
        """
        otra = self._cuenta(
            '41350510', self.cuenta_ingreso,
            cuenta_clase=self.clase_ingreso, cuenta_grupo=self.grupo_ingreso,
        )
        self._poblar()

        self.assertNotIn(otra.codigo, [fila['codigo'] for fila in self._lista()])

    def test_no_arrastra_saldo_anterior(self):
        """El resultado es del periodo, no acumulado desde el principio."""
        self._movimiento(self.venta, date(2025, 12, 1), credito=900)
        self._poblar()

        self.assertEqual(Decimal(self._lista()[0]['saldo']), Decimal(100))


class EstadoSituacionFinancieraTests(_InformePlanoMixin, _InformeBase):
    """
    Es la consulta del estado de resultados sin el piso de clase, tal como sale
    de itrio: trae todas las cuentas que movieron, también las de resultado.
    """

    informe = 'estado_situacion_financiera'
    archivo_excel = 'estado_situacion_financiera.xlsx'
    titulo_excel = 'Estado situacion financiera'
    encabezados_excel = ['Clase', 'Grupo', 'Codigo cuenta', 'Nombre cuenta', 'Saldo ($)']

    def setUp(self):
        super().setUp()
        self.clase_ingreso = ConCuentaClase.objects.create(id=4, nombre='Ingresos')
        self.grupo_ingreso = ConCuentaGrupo.objects.create(id=41, nombre='Operacionales')
        self.cuenta_ingreso = ConCuentaCuenta.objects.create(id=4135, nombre='Comercio')
        self.venta = self._cuenta(
            '41350505', self.cuenta_ingreso,
            cuenta_clase=self.clase_ingreso, cuenta_grupo=self.grupo_ingreso,
        )

    def _poblar(self):
        self._movimiento(self.caja, date(2026, 1, 5), debito=100)

    def test_trae_las_cuentas_de_balance_y_tambien_las_de_resultado(self):
        self._poblar()
        self._movimiento(self.venta, date(2026, 1, 5), credito=100)

        self.assertEqual(
            [fila['codigo'] for fila in self._lista()], ['11050505', '41350505'],
        )

    def test_el_activo_se_lee_negativo(self):
        """
        Consecuencia de compartir la fórmula con el estado de resultados: el
        signo está pensado para ingresos y gastos, no para las cuentas de
        balance. Sale así en itrio y así se replica.
        """
        self._poblar()

        self.assertEqual(Decimal(self._lista()[0]['saldo']), Decimal(-100))



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

    def _crear_contacto(self):
        """El tenant de pruebas no carga fixtures: la cadena ciudad -> estado -> país va acá."""
        pais, _ = GenPais.objects.get_or_create(id=250, nombre='Colombia', codigo='CO')
        estado, _ = GenEstado.objects.get_or_create(id=1, nombre='Antioquia', codigo='05', pais=pais)
        ciudad, _ = GenCiudad.objects.get_or_create(id=1, nombre='Medellín', codigo='05001', estado=estado)
        identificacion, _ = GenIdentificacion.objects.get_or_create(id=6, nombre='NIT', codigo='31')
        tipo_persona, _ = GenTipoPersona.objects.get_or_create(id=1, nombre='Jurídica')
        return GenContacto.objects.create(
            numero_identificacion='900', nombre_corto='Contacto',
            ciudad=ciudad, identificacion=identificacion, tipo_persona=tipo_persona,
            direccion='calle 1', telefono='1', correo='t@t.com',
        )

    def _exigir(self, cuenta, **exigencias):
        for campo, valor in exigencias.items():
            setattr(cuenta, campo, valor)
        cuenta.save(update_fields=list(exigencias))

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

    # --------------------------------------------- exigencias de la cuenta ----

    def test_rechaza_la_cuenta_que_exige_centro_de_costo_y_no_lo_recibe(self):
        """
        Las tres exigencias se respetan en los dos sentidos, igual que las revisa
        `analizar_inconsistencias`: sin el dato el asiento no se escribe a medias.
        """
        self._exigir(self.cuenta_venta, exige_centro_costo=True)
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_rechaza_la_cuenta_que_exige_contacto_y_no_lo_recibe(self):
        self._exigir(self.cuenta_venta, exige_contacto=True)
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_rechaza_la_cuenta_que_exige_base_y_no_la_recibe(self):
        self._exigir(self.cuenta_venta, exige_base=True)
        documento = self._crear_documento(self.factura_tipo)
        self._crear_detalle_item(documento, self._crear_item())

        with self.assertRaises(ValidationError):
            contabilizar.contabilizar([documento.pk])

    def test_no_guarda_el_contacto_en_la_cuenta_que_no_lo_exige(self):
        """El documento trae contacto, pero la cuenta que no lo exige no lo lleva."""
        documento = self._crear_documento(self.factura_tipo, contacto=self._crear_contacto())
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        self.assertEqual(
            {m.contacto_id for m in self._movimientos(documento)}, {None},
        )

    def test_guarda_el_contacto_solo_en_la_cuenta_que_lo_exige(self):
        contacto = self._crear_contacto()
        self._exigir(self.cuenta_cobrar, exige_contacto=True)
        documento = self._crear_documento(self.factura_tipo, contacto=contacto)
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        por_cuenta = {m.cuenta_id: m for m in self._movimientos(documento)}
        self.assertEqual(por_cuenta[self.cuenta_cobrar.pk].contacto_id, contacto.pk)
        self.assertIsNone(por_cuenta[self.cuenta_venta.pk].contacto_id)

    def test_el_asiento_generado_no_tiene_inconsistencias(self):
        """
        Lo que produce `contabilizar` tiene que pasar la revisión que bloquea el
        periodo; si no, el asiento nacería marcado y el periodo no cerraría nunca.
        """
        self._exigir(self.cuenta_cobrar, exige_contacto=True)
        documento = self._crear_documento(self.factura_tipo, contacto=self._crear_contacto())
        self._crear_detalle_item(documento, self._crear_item())

        contabilizar.contabilizar([documento.pk])

        self.assertEqual(analizar_inconsistencias(self.periodo), [])

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


class _MovimientoViewSinPermisos(ConMovimientoViewSet):
    """Variante de la vista sin auth/permiso/throttle para probar el action aislado."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class InconsistenciasMovimientoTests(TenantTestCase):
    """
    Es el mismo análisis que corre `periodo/bloquear`, servido desde movimientos:
    el front lo consulta mientras corrige los asientos, así que tiene que devolver
    el detalle completo sin tocar el estado del periodo —si lo marcara como
    inconsistente, consultar sería un efecto secundario.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        self.comprobante = ConComprobante.objects.create(id=1, nombre='Comprobante')
        self.periodo = ConPeriodo.objects.create(anio=2026, mes=1)
        self.otro = ConPeriodo.objects.create(anio=2026, mes=2)
        self.clase = ConCuentaClase.objects.create(id=1, nombre='Activo')
        self.grupo = ConCuentaGrupo.objects.create(id=11, nombre='Disponible')
        self.cuenta_cuenta = ConCuentaCuenta.objects.create(id=1105, nombre='Caja')
        # `caja` no exige nada: es la contrapartida que cuadra el asiento sin
        # aportar inconsistencias propias.
        self.caja = self._cuenta('11050505')
        self.gasto = self._cuenta('51050505', exige_centro_costo=True)

    def _cuenta(self, codigo, **configuracion):
        configuracion.setdefault('permite_movimiento', True)
        return ConCuenta.objects.create(
            codigo=codigo, nombre=f'Cuenta {codigo}',
            cuenta_clase=self.clase, cuenta_grupo=self.grupo,
            cuenta_cuenta=self.cuenta_cuenta,
            **configuracion,
        )

    def _centro_costo(self):
        return ConCentroCosto.objects.create(nombre='Norte', codigo='N')

    def _contacto(self):
        """El tenant de pruebas no carga fixtures: la cadena ciudad -> estado -> país va acá."""
        pais, _ = GenPais.objects.get_or_create(id=250, nombre='Colombia', codigo='CO')
        estado, _ = GenEstado.objects.get_or_create(id=1, nombre='Antioquia', codigo='05', pais=pais)
        ciudad, _ = GenCiudad.objects.get_or_create(id=1, nombre='Medellín', codigo='05001', estado=estado)
        identificacion, _ = GenIdentificacion.objects.get_or_create(id=6, nombre='NIT', codigo='31')
        tipo_persona, _ = GenTipoPersona.objects.get_or_create(id=1, nombre='Jurídica')
        return GenContacto.objects.create(
            numero_identificacion='900', nombre_corto='Contacto',
            ciudad=ciudad, identificacion=identificacion, tipo_persona=tipo_persona,
            direccion='calle 1', telefono='1', correo='t@t.com',
        )

    def _movimiento(self, cuenta=None, periodo=None, debito=0, credito=0, numero=1,
                    centro_costo=None, contacto=None, base=0):
        return ConMovimiento.objects.create(
            fecha=date(2026, 1, 15),
            numero=numero,
            debito=Decimal(debito),
            credito=Decimal(credito),
            base=Decimal(base),
            naturaleza='D' if debito else 'C',
            comprobante=self.comprobante,
            periodo=periodo or self.periodo,
            cuenta=cuenta or self.caja,
            centro_costo=centro_costo,
            contacto=contacto,
        )

    def _inconsistencias(self):
        return [i['inconsistencia'] for i in self._get({'periodo': self.periodo.id})['inconsistencias']]

    def _get(self, params=None, esperado=200):
        request = APIRequestFactory().get('/contabilidad/movimiento/inconsistencias/', params or {})
        response = _MovimientoViewSinPermisos.as_view({'get': 'inconsistencias'})(request)
        self.assertEqual(response.status_code, esperado)
        return response.data

    def test_periodo_cuadrado_no_reporta_nada(self):
        self._movimiento(debito=1000)
        self._movimiento(credito=1000)
        self.assertEqual(self._get({'periodo': self.periodo.id}), {'inconsistencias': []})

    def test_reporta_el_comprobante_descuadrado(self):
        self._movimiento(debito=1000)
        self._movimiento(credito=900)
        inconsistencias = self._get({'periodo': self.periodo.id})['inconsistencias']
        self.assertEqual(len(inconsistencias), 1)
        self.assertEqual(inconsistencias[0]['comprobante_id'], self.comprobante.id)
        self.assertEqual(inconsistencias[0]['comprobante_nombre'], 'Comprobante')
        self.assertEqual(inconsistencias[0]['inconsistencia'], 'El total de débito y crédito no coinciden')

    def test_reporta_tambien_las_reglas_de_la_cuenta(self):
        """No es solo el descuadre: sale el análisis entero del servicio."""
        self._movimiento(cuenta=self.gasto, debito=1000)
        self._movimiento(credito=1000)
        inconsistencias = self._get({'periodo': self.periodo.id})['inconsistencias']
        self.assertEqual(
            [i['inconsistencia'] for i in inconsistencias],
            ['La cuenta 51050505 exige centro de costo y no tiene centro de costo'],
        )

    def test_solo_mira_el_periodo_pedido(self):
        self._movimiento(periodo=self.otro, debito=1000)
        self.assertEqual(self._get({'periodo': self.periodo.id}), {'inconsistencias': []})
        self.assertEqual(len(self._get({'periodo': self.otro.id})['inconsistencias']), 1)

    def test_no_modifica_el_estado_del_periodo(self):
        """A diferencia de `bloquear`, consultar no marca el periodo como inconsistente."""
        self._movimiento(debito=1000)
        self._get({'periodo': self.periodo.id})
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.estado_inconsistencia)

    def test_sin_periodo_revisa_toda_la_contabilidad(self):
        """El parámetro acota; omitirlo no es un error, revisa todos los periodos."""
        self._movimiento(periodo=self.otro, debito=1000, numero=7)
        inconsistencias = self._get()['inconsistencias']
        self.assertEqual([i['numero'] for i in inconsistencias], [7])

    def test_sin_periodo_no_reporta_lo_que_cuadra(self):
        self._movimiento(debito=1000)
        self._movimiento(credito=1000)
        self._movimiento(periodo=self.otro, debito=500, numero=7)
        self._movimiento(periodo=self.otro, credito=500, numero=7)
        self.assertEqual(self._get(), {'inconsistencias': []})

    def test_periodo_que_no_existe_es_400(self):
        self.assertIn('periodo', self._get({'periodo': self.periodo.id + 50}, esperado=400))

    def test_periodo_que_no_es_numero_es_400(self):
        self.assertIn('periodo', self._get({'periodo': 'enero'}, esperado=400))

    def test_reporta_la_cuenta_que_no_permite_movimiento(self):
        cuenta = self._cuenta('11050510', permite_movimiento=False)
        self._movimiento(cuenta=cuenta, debito=1000)
        self._movimiento(credito=1000)
        self.assertEqual(
            self._inconsistencias(),
            ['La cuenta 11050510 no permite movimientos y tiene movimientos en el periodo'],
        )

    def test_reporta_el_centro_de_costo_que_la_cuenta_no_exige(self):
        """La exigencia se revisa en los dos sentidos: lo que no se exige tampoco puede estar."""
        self._movimiento(debito=1000, centro_costo=self._centro_costo())
        self._movimiento(credito=1000)
        self.assertEqual(
            self._inconsistencias(),
            ['La cuenta 11050505 no exige centro de costo y tiene centro de costo'],
        )

    def test_reporta_el_contacto_que_la_cuenta_no_exige(self):
        self._movimiento(debito=1000, contacto=self._contacto())
        self._movimiento(credito=1000)
        self.assertEqual(
            self._inconsistencias(),
            ['La cuenta 11050505 no exige contacto y tiene contacto'],
        )

    def test_reporta_la_base_que_la_cuenta_no_exige(self):
        self._movimiento(debito=1000, base=500)
        self._movimiento(credito=1000)
        self.assertEqual(
            self._inconsistencias(),
            ['La cuenta 11050505 no exige base y tiene base'],
        )

    def test_no_reporta_lo_que_la_cuenta_si_exige(self):
        cuenta = self._cuenta(
            '52050505', exige_centro_costo=True, exige_contacto=True, exige_base=True,
        )
        self._movimiento(
            cuenta=cuenta, debito=1000,
            centro_costo=self._centro_costo(), contacto=self._contacto(), base=500,
        )
        self._movimiento(credito=1000)
        self.assertEqual(self._inconsistencias(), [])

    def test_reporta_las_tres_exigencias_que_faltan(self):
        cuenta = self._cuenta(
            '52050505', exige_centro_costo=True, exige_contacto=True, exige_base=True,
        )
        self._movimiento(cuenta=cuenta, debito=1000)
        self._movimiento(credito=1000)
        self.assertEqual(
            self._inconsistencias(),
            [
                'La cuenta 52050505 exige centro de costo y no tiene centro de costo',
                'La cuenta 52050505 exige contacto y no tiene contacto',
                'La cuenta 52050505 exige base y no tiene base',
            ],
        )

    def test_reporta_las_tres_que_sobran(self):
        self._movimiento(
            debito=1000,
            centro_costo=self._centro_costo(), contacto=self._contacto(), base=500,
        )
        self._movimiento(credito=1000)
        self.assertEqual(
            self._inconsistencias(),
            [
                'La cuenta 11050505 no exige centro de costo y tiene centro de costo',
                'La cuenta 11050505 no exige contacto y tiene contacto',
                'La cuenta 11050505 no exige base y tiene base',
            ],
        )

    def _documento(self, numero=1, fecha=None, contabilizado=False, contabilidad=True):
        tipo, _ = GenDocumentoTipo.objects.get_or_create(
            pk=901 if contabilidad else 902,
            defaults={
                'nombre': 'FACTURA' if contabilidad else 'COTIZACION',
                'contabilidad': contabilidad,
                'comprobante': self.comprobante,
            },
        )
        return GenDocumento.objects.create(
            documento_tipo=tipo,
            numero=numero,
            fecha=fecha or date(2026, 1, 15),
            estado_contabilizado=contabilizado,
        )

    def test_reporta_cada_documento_sin_contabilizar(self):
        """Uno por documento y no un resumen por tipo: hay que poder abrir el que falta."""
        primero = self._documento(numero=1)
        segundo = self._documento(numero=2)
        inconsistencias = self._get({'periodo': self.periodo.id})['inconsistencias']
        self.assertEqual(
            [(i['documento_id'], i['numero'], i['documento_tipo_nombre']) for i in inconsistencias],
            [(primero.id, 1, 'FACTURA'), (segundo.id, 2, 'FACTURA')],
        )
        self.assertEqual(
            inconsistencias[0]['inconsistencia'],
            'El documento de tipo FACTURA número 1 no está contabilizado',
        )

    def test_el_comprobante_del_movimiento_va_con_su_nombre(self):
        """Las inconsistencias de movimiento nombran el comprobante, no solo su id."""
        self._movimiento(debito=1000, base=500)
        self._movimiento(credito=1000)
        inconsistencia = self._get({'periodo': self.periodo.id})['inconsistencias'][0]
        self.assertEqual(inconsistencia['comprobante_id'], self.comprobante.id)
        self.assertEqual(inconsistencia['comprobante_nombre'], 'Comprobante')

    def test_el_documento_sin_contabilizar_no_tiene_comprobante(self):
        """Sin asiento no hay comprobante que nombrar: las dos claves van en nulo."""
        self._documento()
        inconsistencia = self._get({'periodo': self.periodo.id})['inconsistencias'][0]
        self.assertIsNone(inconsistencia['comprobante_id'])
        self.assertIsNone(inconsistencia['comprobante_nombre'])

    def test_documento_sin_numero_se_identifica_por_id(self):
        documento = self._documento(numero=None)
        inconsistencias = self._get({'periodo': self.periodo.id})['inconsistencias']
        self.assertEqual(
            [i['inconsistencia'] for i in inconsistencias],
            [f'El documento de tipo FACTURA id {documento.id} no está contabilizado'],
        )

    def test_no_reporta_el_documento_ya_contabilizado(self):
        self._documento(contabilizado=True)
        self.assertEqual(self._get({'periodo': self.periodo.id}), {'inconsistencias': []})

    def test_no_reporta_el_documento_de_un_tipo_que_no_es_contable(self):
        self._documento(contabilidad=False)
        self.assertEqual(self._get({'periodo': self.periodo.id}), {'inconsistencias': []})

    def test_el_periodo_acota_los_documentos(self):
        self._documento(fecha=date(2026, 2, 15))
        self.assertEqual(self._get({'periodo': self.periodo.id}), {'inconsistencias': []})
        self.assertEqual(len(self._get()['inconsistencias']), 1)

    def _excel(self, params=None):
        request = APIRequestFactory().get(
            '/contabilidad/movimiento/inconsistencias/', {**(params or {}), 'excel': 'true'},
        )
        response = _MovimientoViewSinPermisos.as_view({'get': 'inconsistencias'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="inconsistencias.xlsx"')
        hoja = load_workbook(BytesIO(response.content)).active
        return [[celda.value for celda in fila] for fila in hoja.rows]

    def test_excel_lleva_encabezados_y_una_fila_por_inconsistencia(self):
        self._movimiento(debito=1000)
        self._movimiento(credito=900)
        filas = self._excel({'periodo': self.periodo.id})
        self.assertEqual(
            filas[0],
            [
                'Comprobante', 'Nombre comprobante', 'Numero', 'Cuenta', 'Documento',
                'Tipo de documento', 'Inconsistencia',
            ],
        )
        self.assertEqual(
            filas[1],
            [
                self.comprobante.id, 'Comprobante', 1, None, None, None,
                'El total de débito y crédito no coinciden',
            ],
        )
        self.assertEqual(len(filas), 2)

    def test_excel_sin_inconsistencias_solo_lleva_encabezados(self):
        self._movimiento(debito=1000)
        self._movimiento(credito=1000)
        self.assertEqual(len(self._excel({'periodo': self.periodo.id})), 1)

    def test_excel_revisa_lo_mismo_que_el_json(self):
        """El parámetro cambia el formato, no lo que se revisa."""
        self._movimiento(cuenta=self.gasto, debito=1000)
        self._movimiento(credito=1000)
        json = self._get({'periodo': self.periodo.id})['inconsistencias']
        filas = self._excel({'periodo': self.periodo.id})[1:]
        self.assertEqual([f[-1] for f in filas], [i['inconsistencia'] for i in json])

    def test_sin_el_parametro_sigue_devolviendo_json(self):
        self._movimiento(debito=1000)
        request = APIRequestFactory().get('/contabilidad/movimiento/inconsistencias/')
        response = _MovimientoViewSinPermisos.as_view({'get': 'inconsistencias'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('inconsistencias', response.data)
