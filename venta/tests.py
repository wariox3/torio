from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.test.cases import TenantTestCase
from openpyxl import Workbook, load_workbook
from rest_framework import permissions
from rest_framework.test import APIRequestFactory, force_authenticate

from rest_framework.exceptions import ValidationError

from general.models import (
    GenCuentaBanco,
    GenCuentaBancoTipo,
    GenDocumento,
    GenDocumentoClase,
    GenDocumentoPago,
    GenDocumentoTipo,
    GenSede,
)
from general.serializers import GenDocumentoCrearSerializer
from general.servicios import documento as documento_servicio
from general.servicios.factura_electronica import CAJERO_POS, _cajero_pos
from seguridad.models import SegUsuario
from venta.models import VenCaja, VenTurno
from venta.views import VenCajaViewSet, VenTurnoViewSet


class _CajaViewSinPermisos(VenCajaViewSet):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class VenCajaTests(TenantTestCase):
    """CRUD de cajas más lista, exportar, importar y seleccionar."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test caja'
        tenant.celular = '+573000000000'
        tenant.correo = 'caja@test.com'

    def setUp(self):
        self.factory = APIRequestFactory()
        self.norte = GenSede.objects.create(nombre='Norte')
        self.sur = GenSede.objects.create(nombre='Sur')
        self.caja1 = VenCaja.objects.create(nombre='Caja 1', placa='PL-1', sede=self.norte)
        self.caja2 = VenCaja.objects.create(nombre='Caja 2', sede=self.sur)
        self.inactiva = VenCaja.objects.create(nombre='Caja vieja', sede=self.norte, estado_activo=False)

    def _llamar(self, metodo, accion, url, datos=None, formato='json', **kwargs):
        vista = _CajaViewSinPermisos.as_view({metodo: accion})
        peticion = getattr(self.factory, metodo)(url, datos, format=formato)
        force_authenticate(peticion, user=SegUsuario(id=1))
        return vista(peticion, **kwargs)

    # ---- CRUD ----

    def test_crear_queda_activa_por_defecto(self):
        respuesta = self._llamar('post', 'create', '/venta/caja/', {
            'nombre': 'Caja 3', 'placa': 'PL-3', 'ubicacion': 'Entrada', 'tipo': 'Registradora',
            'sede': self.norte.id,
        })

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertIs(respuesta.data['estado_activo'], True)
        self.assertEqual(respuesta.data['sede_nombre'], 'Norte')

    def test_crear_sin_sede_da_400(self):
        respuesta = self._llamar('post', 'create', '/venta/caja/', {'nombre': 'Caja 3'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)

    def test_actualizar(self):
        respuesta = self._llamar(
            'patch', 'partial_update', f'/venta/caja/{self.caja1.id}/',
            {'estado_activo': False}, pk=self.caja1.id,
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.caja1.refresh_from_db()
        self.assertIs(self.caja1.estado_activo, False)

    def test_eliminar(self):
        respuesta = self._llamar('delete', 'destroy', f'/venta/caja/{self.caja2.id}/', pk=self.caja2.id)

        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(VenCaja.objects.filter(id=self.caja2.id).exists())

    def test_eliminar_con_documentos_da_400(self):
        tipo = GenDocumentoTipo.objects.create(
            id=24, nombre='POS',
            documento_clase=GenDocumentoClase.objects.create(id=105, nombre='Factura POS'),
        )
        GenDocumento.objects.create(documento_tipo=tipo, fecha=date(2026, 11, 1), caja=self.caja1)

        respuesta = self._llamar('delete', 'destroy', f'/venta/caja/{self.caja1.id}/', pk=self.caja1.id)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)
        self.assertTrue(VenCaja.objects.filter(id=self.caja1.id).exists())

    # ---- lista ----

    def test_lista_filtra_por_sede(self):
        respuesta = self._llamar('post', 'lista', '/venta/caja/lista/', {
            'filtros': [{'propiedad': 'sede_id', 'operador': '=', 'valor': self.norte.id}],
        })

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(
            sorted(c['nombre'] for c in respuesta.data['results']), ['Caja 1', 'Caja vieja'],
        )

    # ---- seleccionar ----

    def test_seleccionar_solo_trae_activas(self):
        respuesta = self._llamar('get', 'seleccionar', '/venta/caja/seleccionar/')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual([c['nombre'] for c in respuesta.data['results']], ['Caja 1', 'Caja 2'])

    def test_seleccionar_filtra_por_sede_y_busqueda(self):
        respuesta = self._llamar('get', 'seleccionar', '/venta/caja/seleccionar/', {'sede_id': self.sur.id})
        self.assertEqual([c['nombre'] for c in respuesta.data['results']], ['Caja 2'])

        respuesta = self._llamar('get', 'seleccionar', '/venta/caja/seleccionar/', {'search': 'pl-1'})
        self.assertEqual([c['nombre'] for c in respuesta.data['results']], ['Caja 1'])

    def test_seleccionar_con_sede_invalida_da_400(self):
        respuesta = self._llamar('get', 'seleccionar', '/venta/caja/seleccionar/', {'sede_id': 'x'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)

    # ---- exportar ----

    def test_exportar(self):
        respuesta = self._llamar('post', 'excel', '/venta/caja/excel/', {})

        self.assertEqual(respuesta.status_code, 200)
        ws = load_workbook(BytesIO(respuesta.content)).active
        filas = [[c.value for c in fila] for fila in ws.iter_rows()]
        self.assertEqual(filas[0], ['ID', 'Nombre', 'Placa', 'Ubicación', 'Tipo', 'Activo', 'Sede', 'Sede nombre'])
        self.assertEqual(len(filas), 4)

    # ---- importar ----

    def _archivo(self, filas):
        wb = Workbook()
        ws = wb.active
        ws.append(['Nombre *', 'Placa', 'Ubicación', 'Tipo', 'Sede (ID) *'])
        for fila in filas:
            ws.append(fila)
        buf = BytesIO()
        wb.save(buf)
        return SimpleUploadedFile(
            'cajas.xlsx', buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _importar(self, filas):
        return self._llamar(
            'post', 'importar', '/venta/caja/importar/', {'archivo': self._archivo(filas)}, formato='multipart',
        )

    def test_importar_crea_las_cajas_activas(self):
        respuesta = self._importar([
            ['Caja 3', 'PL-3', 'Entrada', 'Registradora', self.norte.id],
            ['Caja 1', None, None, None, self.sur.id],  # mismo nombre, otra sede: vale
        ])

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data['creados'], 2)
        nueva = VenCaja.objects.get(nombre='Caja 3')
        self.assertEqual((nueva.placa, nueva.sede_id, nueva.estado_activo), ('PL-3', self.norte.id, True))

    def test_importar_rechaza_repetidas_y_sede_inexistente(self):
        respuesta = self._importar([
            ['Caja 1', None, None, None, self.norte.id],  # ya existe en Norte
            ['Caja 4', None, None, None, 999999],
        ])

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)
        self.assertFalse(VenCaja.objects.filter(nombre='Caja 4').exists())

    def test_importar_ejemplo(self):
        respuesta = self._llamar('get', 'importar_ejemplo', '/venta/caja/importar-ejemplo/')

        self.assertEqual(respuesta.status_code, 200)
        ws = load_workbook(BytesIO(respuesta.content)).active
        self.assertEqual(
            [c.value for c in next(ws.iter_rows())],
            ['Nombre *', 'Placa', 'Ubicación', 'Tipo', 'Sede (ID) *'],
        )


class _TurnoViewSinPermisos(VenTurnoViewSet):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class VenTurnoTests(TenantTestCase):
    """Abrir, facturar en el turno, resumen y cierre con arqueo."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test turno'
        tenant.celular = '+573000000000'
        tenant.correo = 'turno@test.com'

    def setUp(self):
        self.factory = APIRequestFactory()
        self.cajero = SegUsuario.objects.create(
            email='cajero@ejemplo.com', nombre_corto='Ana Cajera', is_active=True, is_verified=True,
        )
        self.otro = SegUsuario.objects.create(email='otro@ejemplo.com', is_active=True, is_verified=True)
        sede = GenSede.objects.create(nombre='Norte')
        self.caja = VenCaja.objects.create(nombre='Caja 1', sede=sede)
        self.caja2 = VenCaja.objects.create(nombre='Caja 2', sede=sede)
        tipo_cuenta = GenCuentaBancoTipo.objects.create(nombre='Caja')
        self.efectivo = GenCuentaBanco.objects.create(nombre='Efectivo', cuenta_banco_tipo=tipo_cuenta)
        self.datafono = GenCuentaBanco.objects.create(nombre='Datáfono', cuenta_banco_tipo=tipo_cuenta)
        self.tipo_pos = GenDocumentoTipo.objects.create(
            id=27, nombre='POS',
            documento_clase=GenDocumentoClase.objects.create(id=105, nombre='Factura POS'),
        )
        self.tipo_factura = GenDocumentoTipo.objects.create(
            id=1, nombre='FACTURA VENTA',
            documento_clase=GenDocumentoClase.objects.create(id=100, nombre='Factura venta'),
        )

    def _llamar(self, metodo, accion, url, datos=None, usuario=None, **kwargs):
        vista = _TurnoViewSinPermisos.as_view({metodo: accion})
        peticion = getattr(self.factory, metodo)(url, datos, format='json')
        force_authenticate(peticion, user=usuario or self.cajero)
        return vista(peticion, **kwargs)

    def _abrir(self, caja=None, base=0, cuenta_banco=None, usuario=None):
        datos = {'caja': (caja or self.caja).id, 'base': base}
        if cuenta_banco is not None:
            datos['cuenta_banco'] = cuenta_banco.id
        return self._llamar('post', 'abrir', '/venta/turno/abrir/', datos, usuario=usuario)

    def _turno(self, base=Decimal('100000')):
        respuesta = self._abrir(base=base, cuenta_banco=self.efectivo)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return VenTurno.objects.get(pk=respuesta.data['id'])

    def _factura(self, turno, total, pagos=(), **campos):
        documento = GenDocumento.objects.create(
            documento_tipo=self.tipo_pos, fecha=date(2026, 11, 4), turno=turno, caja=turno.caja,
            total=Decimal(total), **{'estado_aprobado': True, **campos},
        )
        for cuenta_banco, valor, *anulado in pagos:
            GenDocumentoPago.objects.create(
                documento=documento, cuenta_banco=cuenta_banco, pago=Decimal(valor),
                estado_anulado=bool(anulado),
            )
        return documento

    def _crear_documento(self, datos, usuario=None):
        serializer = GenDocumentoCrearSerializer(
            data={'fecha': '2026-11-04', **datos},
            context={'request': SimpleNamespace(user=usuario or self.cajero)},
        )
        if not serializer.is_valid():
            return serializer.errors
        return serializer.save()

    # ---- abrir ----

    def test_abrir(self):
        respuesta = self._abrir(base=50000, cuenta_banco=self.efectivo)

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data['usuario'], self.cajero.email)
        self.assertIs(respuesta.data['estado_cerrado'], False)
        self.assertEqual(Decimal(respuesta.data['base']), Decimal('50000'))

    def test_una_caja_no_tiene_dos_turnos_abiertos(self):
        self._turno()

        respuesta = self._abrir(usuario=self.otro)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('ya tiene un turno abierto', respuesta.data['detail'])

    def test_un_cajero_no_tiene_dos_turnos_abiertos(self):
        self._turno()

        respuesta = self._abrir(caja=self.caja2)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)

    def test_la_base_pide_cuenta_bancaria(self):
        respuesta = self._abrir(base=1000)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('cuenta bancaria', respuesta.data['detail'])

    def test_no_abre_en_caja_inactiva(self):
        self.caja.estado_activo = False
        self.caja.save()

        respuesta = self._abrir()

        self.assertEqual(respuesta.status_code, 400)

    def test_abierto_devuelve_el_turno_del_usuario(self):
        turno = self._turno()

        self.assertEqual(self._llamar('get', 'abierto', '/venta/turno/abierto/').data['id'], turno.id)
        self.assertEqual(self._llamar('get', 'abierto', '/venta/turno/abierto/', usuario=self.otro).status_code, 404)

    # ---- factura POS en el turno ----

    def test_la_factura_pos_toma_la_caja_del_turno(self):
        turno = self._turno()

        documento = self._crear_documento({'documento_tipo': self.tipo_pos.id, 'turno': turno.id})

        self.assertIsInstance(documento, GenDocumento, documento)
        self.assertEqual((documento.turno_id, documento.caja_id), (turno.id, self.caja.id))

    def test_la_factura_pos_sin_turno_no_se_crea(self):
        errores = self._crear_documento({'documento_tipo': self.tipo_pos.id})

        self.assertIn('turno', errores)

    def test_la_factura_pos_no_entra_en_turno_de_otro_cajero(self):
        turno = self._turno()

        errores = self._crear_documento({'documento_tipo': self.tipo_pos.id, 'turno': turno.id}, usuario=self.otro)

        self.assertIn('otro cajero', str(errores['turno']))

    def test_la_factura_pos_no_entra_en_turno_cerrado(self):
        turno = self._turno(base=0)
        self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {'id': turno.id, 'contados': []})

        errores = self._crear_documento({'documento_tipo': self.tipo_pos.id, 'turno': turno.id})

        self.assertIn('cerrado', str(errores['turno']))

    def test_otro_documento_no_lleva_turno(self):
        turno = self._turno()

        errores = self._crear_documento({'documento_tipo': self.tipo_factura.id, 'turno': turno.id})

        self.assertIn('Solo la factura POS', str(errores['turno']))

    # ---- resumen y cierre ----

    def _escenario(self):
        """Base 100.000 en efectivo; 50.000 en efectivo y 30.000 en datáfono vendidos."""
        turno = self._turno()
        self._factura(turno, '50000', [(self.efectivo, '50000')])
        self._factura(turno, '40000', [(self.datafono, '30000'), (self.efectivo, '10000', 'anulado')])
        # Una factura anulada no cuenta, ni sus pagos.
        self._factura(turno, '7000', [(self.efectivo, '7000')], estado_anulado=True)
        return turno

    def test_resumen_del_turno_abierto(self):
        turno = self._escenario()

        datos = self._llamar('get', 'resumen', f'/venta/turno/{turno.id}/resumen/', pk=turno.id).data

        self.assertEqual(Decimal(datos['total_venta']), Decimal('90000'))
        self.assertEqual(datos['cantidad_documentos'], 2)
        self.assertEqual(
            {c['cuenta_banco_nombre']: Decimal(c['esperado']) for c in datos['cuentas']},
            {'Efectivo': Decimal('150000'), 'Datáfono': Decimal('30000')},
        )

    def test_cerrar_guarda_el_arqueo(self):
        turno = self._escenario()

        respuesta = self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {
            'id': turno.id,
            'contados': [
                {'cuenta_banco': self.efectivo.id, 'valor': '149000'},
                {'cuenta_banco': self.datafono.id, 'valor': '30000'},
            ],
            'comentario': 'Faltan mil',
        })

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertIs(respuesta.data['estado_cerrado'], True)
        self.assertEqual(Decimal(respuesta.data['total_venta']), Decimal('90000'))
        self.assertEqual(respuesta.data['cantidad_documentos'], 2)
        self.assertEqual(
            {d['cuenta_banco_nombre']: (Decimal(d['esperado']), Decimal(d['diferencia']))
             for d in respuesta.data['detalles']},
            {'Efectivo': (Decimal('150000'), Decimal('-1000')), 'Datáfono': (Decimal('30000'), Decimal('0'))},
        )

    def test_cerrar_pide_toda_cuenta_con_algo_esperado(self):
        turno = self._escenario()

        respuesta = self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {
            'id': turno.id, 'contados': [{'cuenta_banco': self.efectivo.id, 'valor': '150000'}],
        })

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Datáfono', respuesta.data['detail'])

    def test_no_cierra_con_facturas_sin_aprobar(self):
        turno = self._turno(base=0)
        self._factura(turno, '1000', estado_aprobado=False)

        respuesta = self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {'id': turno.id, 'contados': []})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('sin aprobar', respuesta.data['detail'])

    def test_no_cierra_dos_veces(self):
        turno = self._turno(base=0)
        self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {'id': turno.id, 'contados': []})

        respuesta = self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {'id': turno.id, 'contados': []})

        self.assertEqual(respuesta.status_code, 400)

    def test_cerrado_la_caja_puede_abrir_otro_turno(self):
        turno = self._turno(base=0)
        self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {'id': turno.id, 'contados': []})

        self.assertEqual(self._abrir(usuario=self.otro).status_code, 201)

    def test_no_se_desaprueba_una_factura_de_turno_cerrado(self):
        turno = self._turno(base=0)
        documento = self._factura(turno, '1000')
        self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {'id': turno.id, 'contados': []})

        with self.assertRaisesMessage(ValidationError, 'turno cerrado'):
            documento_servicio.desaprobar(documento.id)

    # ---- cajero del bloque POS ----

    def test_el_cajero_del_bloque_pos_es_el_del_turno(self):
        turno = self._turno(base=0)
        documento = self._factura(turno, '1000')
        sin_turno = GenDocumento.objects.create(documento_tipo=self.tipo_pos, fecha=date(2026, 11, 4))

        self.assertEqual(_cajero_pos(documento), 'Ana Cajera')
        self.assertEqual(_cajero_pos(sin_turno), CAJERO_POS)

    # ---- imprimir ----

    def _imprimir(self, turno):
        return self._llamar('get', 'imprimir', f'/venta/turno/{turno.id}/imprimir/', pk=turno.id)

    def test_imprimir_el_cierre(self):
        turno = self._escenario()
        self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {
            'id': turno.id,
            'contados': [
                {'cuenta_banco': self.efectivo.id, 'valor': '149000'},
                {'cuenta_banco': self.datafono.id, 'valor': '30000'},
            ],
            'comentario': 'Faltan mil',
        })

        respuesta = self._imprimir(turno)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertIn(f'cierre_turno_{turno.id}.pdf', respuesta['Content-Disposition'])
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_imprimir_un_turno_abierto_es_precierre(self):
        turno = self._escenario()

        respuesta = self._imprimir(turno)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(f'precierre_turno_{turno.id}.pdf', respuesta['Content-Disposition'])

    def test_imprimir_un_turno_sin_ventas(self):
        turno = self._turno(base=0)
        self._llamar('post', 'cerrar', '/venta/turno/cerrar/', {'id': turno.id, 'contados': []})

        self.assertEqual(self._imprimir(turno).status_code, 200)
