"""
Pruebas de lo que vive en el schema público y no entra a ningún contenedor: la
imagen del contenedor, `ingresar`, el panel del staff, `is_staff` en el perfil, y
los adjuntos y solicitudes del master (`CtnModelo`, `CtnArchivo`, `CtnSolicitud`).

Nada de esto toca el schema del tenant, así que los contenedores se crean sin
schema (`auto_create_schema = False` en la instancia): cuesta milisegundos en vez
de las migraciones de un tenant real. Lo que sí necesita un schema —el soporte del
staff— está en `tests_soporte.py`.

Las peticiones van por URL, con JWT, para que corran el middleware y los
`permission_classes` de cada `@action` como en producción.
"""

import io
import re
import uuid as uuid_lib
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import pyotp
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework_simplejwt.tokens import RefreshToken
from tenant_users.permissions.models import UserTenantPermissions

from contenedor import archivo as archivo_servicio
from contenedor.models import (
    CtnArchivo,
    CtnArchivoTipo,
    CtnCliente,
    CtnDominio,
    CtnModelo,
    CtnSolicitud,
    CtnSolicitudTipo,
    CtnSuscripcion,
    CtnSuscripcionTipo,
)
from seguridad import mfa as servicio_mfa
from seguridad.models import SegMfaUsuario, SegUsuario, SegUsuarioCliente
from seguridad.models.mfa_usuario import METODO_TOTP
from seguridad.permissions import EsStaff
from seguridad.serializers import SegUsuarioMeSerializer
from utilidades import backblaze

CDN = 'https://cdn.torio.test'


def _usuario(email, staff=False):
    usuario = SegUsuario.objects.create(email=email, is_active=True, is_verified=True)
    if staff:
        # `is_staff` no es columna del usuario: son sus permisos en el schema público.
        UserTenantPermissions.objects.create(profile=usuario, is_staff=True)
    return usuario


def _contenedor(schema, owner=None, estado=CtnCliente.ESTADO_LISTO, nombre=None, **campos):
    cliente = CtnCliente(
        schema_name=schema, nombre=nombre or f'Contenedor {schema}', celular='+573000000000',
        correo=f'{schema}@ejemplo.com', owner=owner, estado=estado, **campos,
    )
    cliente.auto_create_schema = False
    cliente.save()
    CtnDominio.objects.create(tenant=cliente, domain=f'{schema}.torio.test', is_primary=True)
    return cliente


def _miembro(usuario, cliente, **campos):
    return SegUsuarioCliente.objects.create(usuario=usuario, cliente=cliente, **campos)


def _imagen(formato='PNG'):
    buffer = io.BytesIO()
    Image.new('RGB', (400, 300), 'blue').save(buffer, format=formato)
    tipo = {'PNG': 'image/png', 'JPEG': 'image/jpeg'}[formato]
    return SimpleUploadedFile(f'logo.{formato.lower()}', buffer.getvalue(), content_type=tipo)


def _pdf(nombre='camara.pdf'):
    contenido = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n'
    return SimpleUploadedFile(nombre, contenido, content_type='application/pdf')


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(connection.set_schema_to_public)

    @staticmethod
    def _auth(usuario):
        if usuario is None:
            return {}
        return {'headers': {'authorization': f'Bearer {RefreshToken.for_user(usuario).access_token}'}}

    def _get(self, ruta, usuario=None, **params):
        return self.client.get(ruta, params, **self._auth(usuario))

    def _post(self, ruta, usuario=None, datos=None, multipart=False):
        if multipart:
            return self.client.post(ruta, datos or {}, **self._auth(usuario))
        return self.client.post(ruta, datos or {}, content_type='application/json', **self._auth(usuario))

    def _delete(self, ruta, usuario=None):
        return self.client.delete(ruta, **self._auth(usuario))


# --------------------------------------------------------------------------- #
# Imagen del contenedor
# --------------------------------------------------------------------------- #

@override_settings(B2_CDN_URL_PUBLICO=CDN, B2_BUCKET_PUBLICO='publico')
class ImagenContenedorTests(_Base):

    def setUp(self):
        super().setUp()
        self.owner = _usuario('owner.imagen@ejemplo.com')
        self.miembro = _usuario('miembro.imagen@ejemplo.com')
        self.cliente = _contenedor('imagen_a', owner=self.owner)
        _miembro(self.owner, self.cliente, propietario=True)
        _miembro(self.miembro, self.cliente)
        self.ruta = f'/contenedor/cliente/{self.cliente.id}/imagen/'

    def _subir(self, usuario=None, archivo=None):
        datos = {'imagen': archivo} if archivo is not None else {}
        return self._post(self.ruta, usuario or self.owner, datos, multipart=True)

    def test_el_owner_la_sube_en_dos_tamanos_webp(self):
        with mock.patch.object(backblaze, 'subir') as subir:
            respuesta = self._subir(archivo=_imagen())

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.cliente.refresh_from_db()
        nuevo = self.cliente.imagen_uuid
        self.assertIsNotNone(nuevo)
        prefijo = f'{self.cliente.id}/contenedor/{nuevo}'
        self.assertEqual(
            [(c.args[0], c.args[1], c.args[3]) for c in subir.call_args_list],
            [('publico', f'{prefijo}/original.webp', 'image/webp'),
             ('publico', f'{prefijo}/thumb.webp', 'image/webp')],
        )
        self.assertEqual(respuesta.json()['imagen'], f'{CDN}/{prefijo}/original.webp')
        self.assertEqual(respuesta.json()['imagen_thumbnail'], f'{CDN}/{prefijo}/thumb.webp')

    def test_solo_el_owner(self):
        with mock.patch.object(backblaze, 'subir') as subir:
            respuesta = self._subir(self.miembro, _imagen())
            borrar = self._delete(self.ruta, self.miembro)

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(borrar.status_code, 403)
        subir.assert_not_called()

    def test_un_contenedor_ajeno_no_se_encuentra(self):
        ajeno = _usuario('ajeno.imagen@ejemplo.com')
        self.assertEqual(self._subir(ajeno, _imagen()).status_code, 404)

    def test_sin_archivo_o_con_uno_que_no_es_imagen(self):
        sin_archivo = self._subir()
        texto = SimpleUploadedFile('logo.png', b'no soy una imagen', content_type='image/png')
        with mock.patch.object(backblaze, 'subir') as subir:
            invalida = self._subir(archivo=texto)

        self.assertEqual(sin_archivo.status_code, 400)
        self.assertIn('detail', sin_archivo.json())
        self.assertEqual(invalida.status_code, 400)
        self.assertIn('detail', invalida.json())
        subir.assert_not_called()

    def test_reemplazarla_borra_el_juego_anterior(self):
        with mock.patch.object(backblaze, 'subir'):
            self._subir(archivo=_imagen())
            self.cliente.refresh_from_db()
            anterior = self.cliente.imagen_uuid
            with mock.patch.object(backblaze, 'eliminar') as eliminar:
                self._subir(archivo=_imagen('JPEG'))

        self.cliente.refresh_from_db()
        self.assertNotEqual(self.cliente.imagen_uuid, anterior)
        self.assertEqual(sorted(c.args[1] for c in eliminar.call_args_list), [
            f'{self.cliente.id}/contenedor/{anterior}/original.webp',
            f'{self.cliente.id}/contenedor/{anterior}/thumb.webp',
        ])

    def test_quitarla_es_idempotente(self):
        with mock.patch.object(backblaze, 'subir'):
            self._subir(archivo=_imagen())

        with mock.patch.object(backblaze, 'eliminar') as eliminar:
            primera = self._delete(self.ruta, self.owner)
            segunda = self._delete(self.ruta, self.owner)

        self.assertEqual((primera.status_code, segunda.status_code), (200, 200))
        self.assertIsNone(primera.json()['imagen'])
        self.assertEqual(eliminar.call_count, 2)  # original y thumb, solo la primera vez
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.imagen_uuid)

    def test_eliminar_el_contenedor_borra_su_imagen_de_b2(self):
        imagen_uuid = uuid_lib.uuid4()
        CtnCliente.objects.filter(pk=self.cliente.pk).update(imagen_uuid=imagen_uuid)
        cliente_id = self.cliente.id

        with mock.patch.object(CtnCliente, 'es_superusuario', return_value=True), \
                mock.patch.object(backblaze, 'eliminar') as eliminar:
            respuesta = self._delete(f'/contenedor/cliente/{cliente_id}/', self.owner)

        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(sorted(c.args[1] for c in eliminar.call_args_list), [
            f'{cliente_id}/contenedor/{imagen_uuid}/original.webp',
            f'{cliente_id}/contenedor/{imagen_uuid}/thumb.webp',
        ])

    def test_lista_usuario_trae_las_urls(self):
        imagen_uuid = uuid_lib.uuid4()
        CtnCliente.objects.filter(pk=self.cliente.pk).update(imagen_uuid=imagen_uuid)

        fila = self._get('/contenedor/cliente/lista-usuario/', self.owner).json()['results'][0]

        prefijo = f'{CDN}/{self.cliente.id}/contenedor/{imagen_uuid}'
        self.assertEqual(fila['cliente_imagen'], f'{prefijo}/original.webp')
        self.assertEqual(fila['cliente_imagen_thumbnail'], f'{prefijo}/thumb.webp')

    def test_sin_imagen_las_urls_son_nulas(self):
        fila = self._get('/contenedor/cliente/lista-usuario/', self.owner).json()['results'][0]
        self.assertIsNone(fila['cliente_imagen'])
        self.assertIsNone(fila['cliente_imagen_thumbnail'])
        detalle = self._get(f'/contenedor/cliente/{self.cliente.id}/', self.owner).json()
        self.assertIsNone(detalle['imagen'])


# --------------------------------------------------------------------------- #
# Ingresar
# --------------------------------------------------------------------------- #

class IngresarTests(_Base):

    def setUp(self):
        super().setUp()
        self.miembro = _usuario('miembro.ingresar@ejemplo.com')
        self.cliente = _contenedor('ingresar_a')
        _miembro(self.miembro, self.cliente)

    def _ingresar(self, cliente=None, usuario=None):
        cliente = cliente or self.cliente
        return self._post(f'/contenedor/cliente/{cliente.id}/ingresar/', usuario or self.miembro)

    def test_marca_la_ultima_conexion(self):
        CtnCliente.objects.filter(pk=self.cliente.pk).update(
            fecha_ultima_conexion=timezone.now() - timedelta(days=5),
        )
        antes = timezone.now()

        respuesta = self._ingresar()

        self.assertEqual(respuesta.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertGreaterEqual(self.cliente.fecha_ultima_conexion, antes)
        self.assertIn('fecha_ultima_conexion', respuesta.json())

    def test_un_no_miembro_recibe_404(self):
        ajeno = _usuario('ajeno.ingresar@ejemplo.com')
        self.assertEqual(self._ingresar(usuario=ajeno).status_code, 404)

    def test_uno_que_no_esta_listo_responde_409(self):
        for estado in (CtnCliente.ESTADO_CREANDO, CtnCliente.ESTADO_ERROR):
            with self.subTest(estado=estado):
                cliente = _contenedor(f'ingresar_{estado}', estado=estado)
                _miembro(self.miembro, cliente)

                respuesta = self._ingresar(cliente)

                self.assertEqual(respuesta.status_code, 409)
                self.assertIn('detail', respuesta.json())

    def test_lista_usuario_expone_la_ultima_conexion(self):
        self._ingresar()
        self.cliente.refresh_from_db()

        fila = self._get('/contenedor/cliente/lista-usuario/', self.miembro).json()['results'][0]

        self.assertEqual(
            fila['cliente_fecha_ultima_conexion'],
            self.cliente.fecha_ultima_conexion.astimezone(timezone.get_current_timezone()).isoformat(),
        )


# --------------------------------------------------------------------------- #
# Panel del staff
# --------------------------------------------------------------------------- #

class PanelStaffTests(_Base):
    RUTA = '/contenedor/cliente/administrar/'

    def setUp(self):
        super().setUp()
        self.staff = _usuario('staff.panel@ejemplo.com', staff=True)
        self.owner = _usuario('owner.panel@ejemplo.com')
        self.tipo = CtnSuscripcionTipo.objects.create(
            id=97, nombre='Plan panel', precio=0, suscripcion_categoria_id=97,
        )
        self.alfa = _contenedor('panel_alfa', owner=self.owner, nombre='Alfa')
        self.beta = _contenedor('panel_beta', nombre='Beta', estado=CtnCliente.ESTADO_ERROR, activo=False)
        _miembro(self.owner, self.alfa, propietario=True)
        _miembro(_usuario('otro.panel@ejemplo.com'), self.alfa)

    def _suscribir(self, cliente, fecha_fin):
        suscripcion = CtnSuscripcion.objects.create(
            cliente=cliente, usuario=self.owner, suscripcion_tipo=self.tipo,
            fecha_inicio=fecha_fin - timedelta(days=30), fecha_fin=fecha_fin,
            frecuencia=CtnSuscripcion.FRECUENCIA_PRUEBA,
        )
        CtnCliente.objects.filter(pk=cliente.pk).update(suscripcion=suscripcion)

    def _filas(self, **params):
        respuesta = self._get(self.RUTA, self.staff, **params)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return {fila['schema_name']: fila for fila in respuesta.json()['results']}

    def test_anonimo_401(self):
        self.assertEqual(self._get(self.RUTA).status_code, 401)

    def test_no_staff_403_aunque_sea_owner(self):
        respuesta = self._get(self.RUTA, self.owner)
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('detail', respuesta.json())

    def test_dentro_de_un_contenedor_no_es_staff(self):
        """`is_staff` fuera del público diría si es staff de ese contenedor: se niega."""
        peticion = SimpleNamespace(user=self.staff)
        dentro = SimpleNamespace(schema_name='panel_alfa')

        with mock.patch.object(connection, 'tenant', dentro):
            self.assertFalse(EsStaff().has_permission(peticion, None))
        self.assertTrue(EsStaff().has_permission(peticion, None))

    def test_con_x_tenant_la_ruta_no_existe(self):
        respuesta = self.client.get(
            self.RUTA, headers={**self._auth(self.staff)['headers'], 'x-tenant': 'panel_alfa'},
        )
        self.assertIn(respuesta.status_code, (403, 404))

    def test_ve_todos_los_contenedores_menos_el_publico(self):
        _contenedor('public', nombre='Público')

        filas = self._filas()

        self.assertEqual(set(filas), {'panel_alfa', 'panel_beta'})
        alfa = filas['panel_alfa']
        self.assertEqual(alfa['usuarios'], 2)
        self.assertEqual(alfa['owner_email'], 'owner.panel@ejemplo.com')
        self.assertEqual(alfa['dominio'], 'panel_alfa.torio.test')
        self.assertIsNone(alfa['soporte_id'])
        self.assertEqual(filas['panel_beta']['usuarios'], 0)
        self.assertIsNone(filas['panel_beta']['owner_email'])

    def test_suscripcion_vigente_hasta_la_fecha_fin_inclusive(self):
        hoy = timezone.localdate()
        self._suscribir(self.alfa, hoy)
        self._suscribir(self.beta, hoy - timedelta(days=1))
        sin = _contenedor('panel_gama', nombre='Gama')

        filas = self._filas()

        self.assertIs(filas['panel_alfa']['suscripcion_vigente'], True)
        self.assertIs(filas['panel_beta']['suscripcion_vigente'], False)
        self.assertIs(filas[sin.schema_name]['suscripcion_vigente'], False)
        self.assertEqual(set(self._filas(suscripcion_vigente='true')), {'panel_alfa'})
        self.assertEqual(set(self._filas(suscripcion_vigente='false')), {'panel_beta', 'panel_gama'})

    def test_filtros(self):
        self.assertEqual(set(self._filas(nombre='alf')), {'panel_alfa'})
        self.assertEqual(set(self._filas(nombre='PANEL_BE')), {'panel_beta'})  # también por schema
        self.assertEqual(set(self._filas(estado='error')), {'panel_beta'})
        self.assertEqual(set(self._filas(activo='false')), {'panel_beta'})
        self.assertEqual(set(self._filas(activo='true')), {'panel_alfa'})

    def test_filtros_invalidos_400_con_detail(self):
        for params in ({'estado': 'borrado'}, {'activo': 'quizas'}, {'suscripcion_vigente': '1'}):
            with self.subTest(params=params):
                respuesta = self._get(self.RUTA, self.staff, **params)
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(list(respuesta.json()), ['detail'])

    def test_pagina_de_25(self):
        for indice in range(25):
            _contenedor(f'panel_lote_{indice:02d}')

        datos = self._get(self.RUTA, self.staff).json()

        self.assertEqual(datos['count'], 27)
        self.assertEqual(len(datos['results']), 25)
        self.assertIsNotNone(datos['next'])


# --------------------------------------------------------------------------- #
# `is_staff` en el perfil
# --------------------------------------------------------------------------- #

class IsStaffPerfilTests(_Base):
    CLAVE = 'clave-de-prueba-123'

    def setUp(self):
        super().setUp()
        self.staff = _usuario('staff.perfil@ejemplo.com', staff=True)
        self.normal = _usuario('normal.perfil@ejemplo.com')
        for usuario in (self.staff, self.normal):
            usuario.set_password(self.CLAVE)
            usuario.save()

    def _login(self, usuario):
        return self.client.post('/seguridad/login/', {'email': usuario.email, 'password': self.CLAVE})

    def test_en_el_login(self):
        self.assertIs(self._login(self.staff).json()['is_staff'], True)
        self.assertIs(self._login(self.normal).json()['is_staff'], False)

    def test_en_el_login_con_mfa(self):
        secreto = servicio_mfa.generar_secreto()
        SegMfaUsuario.objects.create(
            usuario=self.staff, metodo=METODO_TOTP, secreto=servicio_mfa.cifrar_secreto(secreto),
            activo=True, fecha_activacion=timezone.now(),
        )
        token = self._login(self.staff).json()['mfa_token']

        respuesta = self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token, 'codigo': pyotp.TOTP(secreto).now(),
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertIs(respuesta.json()['is_staff'], True)

    def test_en_el_usuario_actual(self):
        self.assertIs(self._get('/seguridad/me/', self.staff).json()['is_staff'], True)
        self.assertIs(self._get('/seguridad/me/', self.normal).json()['is_staff'], False)

    def test_con_un_tenant_activo_es_false(self):
        with mock.patch.object(connection, 'tenant', SimpleNamespace(schema_name='otro')):
            self.assertIs(SegUsuarioMeSerializer(self.staff).data['is_staff'], False)
        staff = SegUsuario.objects.get(pk=self.staff.pk)
        self.assertIs(SegUsuarioMeSerializer(staff).data['is_staff'], True)


# --------------------------------------------------------------------------- #
# CtnModelo, CtnArchivo y CtnSolicitud
# --------------------------------------------------------------------------- #

class CatalogoModeloTests(TestCase):

    def test_cargar_geodata_siembra_ctn_modelo_y_es_idempotente(self):
        call_command('cargar_geodata', stdout=io.StringIO())
        call_command('cargar_geodata', stdout=io.StringIO())

        modelo = CtnModelo.objects.get(pk=1)
        self.assertEqual((modelo.app, modelo.clase, modelo.tipo), ('contenedor', 'CtnSolicitud', 'M'))
        self.assertEqual(CtnModelo.objects.filter(pk=1).count(), 1)
        self.assertEqual(sorted(CtnArchivoTipo.objects.values_list('id', flat=True)), [1, 2, 3])
        self.assertTrue(CtnSolicitudTipo.objects.filter(pk=1).exists())


@override_settings(B2_BUCKET_PRIVADO='privado')
class SolicitudYArchivoTests(_Base):

    def setUp(self):
        super().setUp()
        self.modelo = CtnModelo.objects.create(
            id=1, app='contenedor', clase='CtnSolicitud', nombre='Solicitud', tipo='M',
        )
        self.camara = CtnArchivoTipo.objects.create(id=1, codigo='camara_comercio', nombre='Cámara')
        self.certificado = CtnSolicitudTipo.objects.create(id=1, codigo='certificado_firma', nombre='Certificado')
        self.miembro = _usuario('miembro.solicitud@ejemplo.com')
        self.ajeno = _usuario('ajeno.solicitud@ejemplo.com')
        self.cliente = _contenedor('solicitud_a')
        self.otro = _contenedor('solicitud_b')
        _miembro(self.miembro, self.cliente)
        _miembro(self.ajeno, self.otro)

    def _solicitar(self, quien=None, **datos):
        datos = {'cliente': self.cliente.id, 'solicitud_tipo': self.certificado.id, **datos}
        return self._post('/contenedor/solicitud/', quien or self.miembro, datos)

    def _adjuntar(self, objeto_id, usuario=None, modelo=None, archivo=None):
        return self._post('/contenedor/archivo/', usuario or self.miembro, {
            'archivo': archivo or _pdf(), 'modelo': (modelo or self.modelo).id,
            'objeto_id': objeto_id, 'archivo_tipo': self.camara.id,
        }, multipart=True)

    @staticmethod
    def _sin_ids(texto):
        return re.sub(r'\d+', 'N', texto)

    # ---- solicitud ----

    def test_nace_pendiente_y_con_quien_la_pide(self):
        respuesta = self._solicitar(comentario='Para facturar')

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        datos = respuesta.json()
        self.assertEqual(datos['estado'], 'pendiente')
        self.assertEqual(datos['usuario'], self.miembro.id)
        self.assertEqual(datos['solicitud_tipo_nombre'], 'Certificado')
        solicitud = CtnSolicitud.objects.get(pk=datos['id'])
        self.assertEqual((solicitud.cliente_id, solicitud.comentario), (self.cliente.id, 'Para facturar'))

    def test_no_deja_escribir_estado_ni_usuario(self):
        respuesta = self._solicitar(estado='atendida', usuario=self.ajeno.id)

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()['estado'], 'pendiente')
        self.assertEqual(respuesta.json()['usuario'], self.miembro.id)

    def test_un_contenedor_ajeno_responde_como_uno_inexistente(self):
        ajeno = self._solicitar(cliente=self.otro.id)
        inexistente = self._solicitar(cliente=999999)

        self.assertEqual((ajeno.status_code, inexistente.status_code), (400, 400))
        self.assertIn('cliente', ajeno.json())
        self.assertEqual(self._sin_ids(ajeno.json()['detail']), self._sin_ids(inexistente.json()['detail']))
        self.assertFalse(CtnSolicitud.objects.exists())

    def test_una_segunda_pendiente_del_mismo_tipo_409(self):
        self._solicitar()

        respuesta = self._solicitar()

        self.assertEqual(respuesta.status_code, 409)
        self.assertIn('detail', respuesta.json())
        self.assertEqual(CtnSolicitud.objects.count(), 1)

    def test_en_carrera_el_indice_unico_tambien_da_409(self):
        self._solicitar()
        exists = QuerySet.exists

        def exists_sin_pendientes(qs):
            # La consulta de la vista no ve la otra: como si llegaran a la vez.
            if qs.model is CtnSolicitud:
                return False
            return exists(qs)

        with mock.patch.object(QuerySet, 'exists', exists_sin_pendientes):
            respuesta = self._solicitar()

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(CtnSolicitud.objects.count(), 1)

    def test_otro_tipo_o_una_ya_atendida_si_entran(self):
        otro_tipo = CtnSolicitudTipo.objects.create(id=2, codigo='otro', nombre='Otro')
        primera = self._solicitar().json()['id']

        self.assertEqual(self._solicitar(solicitud_tipo=otro_tipo.id).status_code, 201)
        CtnSolicitud.objects.filter(pk=primera).update(estado=CtnSolicitud.ESTADO_ATENDIDA)
        self.assertEqual(self._solicitar().status_code, 201)

    # ---- archivo ----

    def test_adjunta_a_la_solicitud_de_punta_a_punta(self):
        solicitud_id = self._solicitar().json()['id']

        with mock.patch.object(backblaze, 'subir') as subir:
            respuesta = self._adjuntar(solicitud_id)

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        datos = respuesta.json()
        self.assertEqual(datos['cliente'], self.cliente.id)
        self.assertEqual(datos['objeto_id'], str(solicitud_id))
        self.assertEqual(datos['archivo_tipo_codigo'], 'camara_comercio')
        self.assertEqual(datos['nombre'], 'camara.pdf')
        self.assertNotIn('almacenamiento_id', datos)
        archivo = CtnArchivo.objects.get(pk=datos['id'])
        self.assertEqual(archivo.almacenamiento_id, f'{self.cliente.id}/master/1/{archivo.uuid}.pdf')
        self.assertEqual(subir.call_args.kwargs['bucket'], 'privado')
        self.assertEqual(subir.call_args.kwargs['key'], archivo.almacenamiento_id)

    def test_el_cliente_sale_del_objeto_no_del_request(self):
        solicitud_id = self._solicitar().json()['id']

        with mock.patch.object(backblaze, 'subir'):
            respuesta = self._post('/contenedor/archivo/', self.miembro, {
                'archivo': _pdf(), 'modelo': 1, 'objeto_id': solicitud_id,
                'archivo_tipo': self.camara.id, 'cliente': self.otro.id,
            }, multipart=True)

        self.assertEqual(respuesta.json()['cliente'], self.cliente.id)

    def test_no_miembro_e_inexistente_dan_el_mismo_400(self):
        solicitud_id = self._solicitar().json()['id']

        with mock.patch.object(backblaze, 'subir') as subir:
            ajeno = self._adjuntar(solicitud_id, usuario=self.ajeno)
            inexistente = self._adjuntar(999999, usuario=self.ajeno)

        self.assertEqual((ajeno.status_code, inexistente.status_code), (400, 400))
        self.assertEqual(
            self._sin_ids(ajeno.json()['detail']), self._sin_ids(inexistente.json()['detail']),
        )
        self.assertEqual(
            [self._sin_ids(m) for m in ajeno.json()['objeto_id']],
            [self._sin_ids(m) for m in inexistente.json()['objeto_id']],
        )
        subir.assert_not_called()

    def test_un_modelo_sin_cliente_no_admite_adjuntos(self):
        pais = CtnModelo.objects.create(id=2, app='contenedor', clase='CtnPais', nombre='País')

        respuesta = self._adjuntar(1, modelo=pais)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('no admite adjuntos', respuesta.json()['detail'])

    def test_un_archivo_no_permitido_400(self):
        solicitud_id = self._solicitar().json()['id']
        falso = SimpleUploadedFile('rut.pdf', b'no soy un pdf', content_type='application/pdf')

        with mock.patch.object(backblaze, 'subir') as subir:
            respuesta = self._adjuntar(solicitud_id, archivo=falso)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('archivo', respuesta.json())
        subir.assert_not_called()

    def test_si_falla_el_insert_se_borra_de_b2(self):
        solicitud = CtnSolicitud.objects.create(cliente=self.cliente, solicitud_tipo=self.certificado)

        with (
            mock.patch.object(backblaze, 'subir') as subir,
            mock.patch.object(backblaze, 'eliminar') as eliminar,
            mock.patch.object(CtnArchivo.objects, 'create', side_effect=DatabaseError('caída')),
            self.assertRaises(DatabaseError),
        ):
            archivo_servicio.subir(_pdf(), self.modelo, solicitud, self.camara)

        eliminar.assert_called_once_with('privado', subir.call_args.kwargs['key'])

    def test_borrar_el_contenedor_deja_el_archivo_sin_cliente(self):
        archivo = CtnArchivo.objects.create(
            cliente=self.cliente, modelo=self.modelo, objeto_id='1', archivo_tipo=self.camara,
            nombre='rut.pdf', tipo='application/pdf', almacenamiento_id='x',
        )

        self.cliente.delete(force_drop=True)

        archivo.refresh_from_db()
        self.assertIsNone(archivo.cliente_id)
