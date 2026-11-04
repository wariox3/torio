from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.test.cases import TenantTestCase
from openpyxl import Workbook, load_workbook
from rest_framework import permissions
from rest_framework.test import APIRequestFactory, force_authenticate

from general.models import GenDocumento, GenDocumentoClase, GenDocumentoTipo, GenSede
from seguridad.models import SegUsuario
from venta.models import VenCaja
from venta.views import VenCajaViewSet


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
