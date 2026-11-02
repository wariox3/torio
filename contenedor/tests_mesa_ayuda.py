"""
Mesa de ayuda: `POST /contenedor/mesa-ayuda/caso/`.

Vive en el schema público y no toca ningún contenedor. Carbono se reemplaza con
un mock de `Carbono.caso_nuevo`, así que acá se prueba lo que hace torio: qué
datos manda, qué adjuntos deja pasar y cómo traduce la respuesta de carbono.
"""

from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from contenedor.views import mesa_ayuda
from seguridad.models import SegUsuario
from utilidades.carbono import Carbono

RUTA = '/contenedor/mesa-ayuda/caso/'
RUTA_LISTA = '/contenedor/mesa-ayuda/caso/lista/'
MB = 1024 * 1024


def _archivo(nombre='captura.png', tamano=10, tipo='image/png'):
    return SimpleUploadedFile(nombre, b'x' * tamano, content_type=tipo)


def _ok(datos=None):
    return {'error': False, 'status': 200, 'datos': {'id': 77, 'adjuntosFallidos': 0, **(datos or {})}}


class CasoTests(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(connection.set_schema_to_public)
        self.usuario = SegUsuario.objects.create(
            email='usuario.mesa@ejemplo.com', nombre_corto='Usuario Mesa', celular='3001234567',
            is_active=True, is_verified=True,
        )
        self.auth = {'authorization': f'Bearer {RefreshToken.for_user(self.usuario).access_token}'}

    def _json(self, datos, respuesta=None):
        with mock.patch.object(Carbono, 'caso_nuevo', return_value=respuesta or _ok()) as caso:
            r = self.client.post(RUTA, datos, content_type='application/json', headers=self.auth)
        return r, caso

    def _multipart(self, datos, respuesta=None):
        with mock.patch.object(Carbono, 'caso_nuevo', return_value=respuesta or _ok()) as caso:
            r = self.client.post(RUTA, datos, headers=self.auth)
        return r, caso

    def test_sin_adjuntos_en_json_sigue_funcionando(self):
        r, caso = self._json({'tipo': 'SOP', 'descripcion': 'No me deja entrar'})

        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json(), {'id': 77, 'adjuntos_fallidos': 0})
        kwargs = caso.call_args.kwargs
        self.assertEqual(kwargs['archivos'], [])
        self.assertEqual(kwargs['correo'], 'usuario.mesa@ejemplo.com')
        self.assertEqual(kwargs['telefono'], '3001234567')
        self.assertEqual(kwargs['modulo'], mesa_ayuda.MODULO_GENERAL)
        self.assertEqual(kwargs['usuario_integracion'], self.usuario.id)

    def test_usuario_integracion_sale_de_la_sesion_no_del_body(self):
        r, caso = self._json({'tipo': 'SOP', 'descripcion': 'x', 'usuario_integracion': 999999})

        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(caso.call_args.kwargs['usuario_integracion'], self.usuario.id)

    def test_con_adjuntos_los_manda_a_carbono(self):
        r, caso = self._multipart({
            'tipo': 'ERR', 'descripcion': 'Sale un error',
            'archivos': [_archivo('a.png'), _archivo('b.pdf', tipo='application/pdf')],
        })

        self.assertEqual(r.status_code, 201, r.content)
        archivos = caso.call_args.kwargs['archivos']
        self.assertEqual([(nombre, mime) for nombre, _, mime in archivos],
                         [('a.png', 'image/png'), ('b.pdf', 'application/pdf')])

    def test_devuelve_los_adjuntos_que_carbono_no_guardo(self):
        r, _ = self._multipart(
            {'tipo': 'ERR', 'descripcion': 'Sale un error', 'archivos': [_archivo()]},
            respuesta=_ok({'adjuntosFallidos': 1}),
        )

        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['adjuntos_fallidos'], 1)

    def test_mas_de_cinco_archivos_es_400(self):
        archivos = [_archivo(f'{i}.png') for i in range(mesa_ayuda.MAXIMO_ADJUNTOS + 1)]
        r, caso = self._multipart({'tipo': 'SOP', 'descripcion': 'x', 'archivos': archivos})

        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('detail', r.json())
        caso.assert_not_called()

    def test_un_archivo_de_mas_de_10_mb_es_400(self):
        r, caso = self._multipart({
            'tipo': 'SOP', 'descripcion': 'x', 'archivos': [_archivo('grande.png', 10 * MB + 1)],
        })

        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('grande.png', r.json()['detail'])
        caso.assert_not_called()

    def test_mas_de_20_mb_entre_todos_es_400(self):
        archivos = [_archivo(f'{i}.png', 7 * MB) for i in range(3)]
        r, caso = self._multipart({'tipo': 'SOP', 'descripcion': 'x', 'archivos': archivos})

        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('20 MB', r.json()['detail'])
        caso.assert_not_called()

    def test_un_400_de_carbono_pasa_su_mensaje(self):
        r, _ = self._json(
            {'tipo': 'SOP', 'descripcion': 'x'},
            respuesta={'error': True, 'status': 400, 'datos': {'mensaje': 'Descripción muy corta'}},
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['detail'], 'Descripción muy corta')

    def test_otra_falla_de_carbono_es_502_sin_exponerla(self):
        r, _ = self._json(
            {'tipo': 'SOP', 'descripcion': 'x'},
            respuesta={'error': True, 'status': 401, 'datos': {'mensaje': 'Token inválido'}},
        )

        self.assertEqual(r.status_code, 502)
        self.assertNotIn('Token', r.json()['detail'])

    def test_sin_sesion_es_401(self):
        r = self.client.post(RUTA, {'tipo': 'SOP', 'descripcion': 'x'}, content_type='application/json')

        self.assertEqual(r.status_code, 401)


class CasoListaTests(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(connection.set_schema_to_public)
        self.usuario = SegUsuario.objects.create(
            email='lista.mesa@ejemplo.com', is_active=True, is_verified=True,
        )
        self.auth = {'authorization': f'Bearer {RefreshToken.for_user(self.usuario).access_token}'}

    def _get(self, respuesta, **params):
        with mock.patch.object(Carbono, 'caso_lista_usuario_integracion', return_value=respuesta) as lista:
            r = self.client.get(RUTA_LISTA, params, headers=self.auth)
        return r, lista

    def test_lista_los_casos_del_usuario_en_snake_case(self):
        r, lista = self._get({'error': False, 'status': 200, 'datos': {'casos': [{
            'id': 9, 'descripcion': 'No carga', 'estadoAtendido': True,
            'estadoRespuesta': False, 'estadoCerrado': False,
        }]}})

        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), [{
            'id': 9, 'descripcion': 'No carga', 'estado_atendido': True,
            'estado_respuesta': False, 'estado_cerrado': False,
        }])
        lista.assert_called_once_with(usuario_integracion=self.usuario.id, correo=self.usuario.email)

    def test_id_y_correo_salen_de_la_sesion_no_de_los_parametros(self):
        r, lista = self._get(
            {'error': False, 'status': 200, 'datos': {'casos': []}},
            usuario_integracion=999999, correo='otro@ejemplo.com',
        )

        self.assertEqual(r.status_code, 200, r.content)
        lista.assert_called_once_with(usuario_integracion=self.usuario.id, correo=self.usuario.email)

    def test_una_falla_de_carbono_es_502(self):
        r, _ = self._get({'error': True, 'status': 400, 'datos': {'mensaje': 'El correo es obligatorio'}})

        self.assertEqual(r.status_code, 502)
        self.assertIn('detail', r.json())

    def test_no_gasta_el_cupo_de_crear_casos(self):
        for _ in range(12):
            r, _ = self._get({'error': False, 'status': 200, 'datos': {'casos': []}})
        self.assertEqual(r.status_code, 200)

    def test_sin_sesion_es_401(self):
        self.assertEqual(self.client.get(RUTA_LISTA).status_code, 401)


@override_settings(CARBONO_KEY='clave', CARBONO_URL='https://carbono.test')
class ClienteCarbonoTests(TestCase):
    """Lo que de verdad le llega a carbono: sus nombres de campo, en camelCase."""

    def _httpx(self, json):
        parche = mock.patch('utilidades.carbono.httpx.request')
        request = parche.start()
        self.addCleanup(parche.stop)
        request.return_value.status_code = 200
        request.return_value.json.return_value = json
        return request

    def test_caso_nuevo_manda_usuario_integracion_en_camel_case(self):
        request = self._httpx({'id': 1, 'adjuntosFallidos': 0})

        Carbono().caso_nuevo('SOP', 'Ana', 'ana@ejemplo.com', '1', 'x', 'Ana', 'GEN', usuario_integracion=42)

        metodo, url = request.call_args.args
        self.assertEqual((metodo, url), ('POST', 'https://carbono.test/api/soporte/caso/nuevo'))
        self.assertEqual(request.call_args.kwargs['data']['usuarioIntegracion'], 42)

    def test_lista_manda_usuario_integracion_y_correo(self):
        request = self._httpx({'casos': []})

        respuesta = Carbono().caso_lista_usuario_integracion(42, 'ana@ejemplo.com')

        self.assertFalse(respuesta['error'])
        metodo, url = request.call_args.args
        self.assertEqual(
            (metodo, url), ('GET', 'https://carbono.test/api/soporte/caso/lista-usuario-integracion'),
        )
        self.assertEqual(
            request.call_args.kwargs['params'], {'usuarioIntegracion': 42, 'correo': 'ana@ejemplo.com'},
        )
