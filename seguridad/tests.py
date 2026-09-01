import io
import time
from datetime import timedelta
from unittest.mock import patch

import pyotp
from botocore.exceptions import ConnectionClosedError
from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from django.conf import settings
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from seguridad import acceso as servicio_acceso
from seguridad import foto
from seguridad import mfa as servicio_mfa
from seguridad.serializers import SegUsuarioMeSerializer
from utilidades import backblaze, imagenes
from utilidades.telefono import a_nacional, normalizar_e164
from seguridad.models import (
    METODO_CORREO,
    METODO_SMS,
    METODO_TOTP,
    METODOS,
    RESULTADO_CLAVE,
    RESULTADO_MFA_FALLIDO,
    RESULTADO_MFA_PENDIENTE,
    RESULTADO_NO_VERIFICADO,
    RESULTADO_OK,
    SegAcceso,
    SegMfaCodigoRespaldo,
    SegMfaDesafio,
    SegMfaUsuario,
    SegUsuario,
)

# Clave propia para los tests: no dependen de la que haya en el `.env` del entorno.
_CLAVE_MFA = Fernet.generate_key().decode()


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA)
class MfaBaseTests(TestCase):
    def setUp(self):
        self.usuario = SegUsuario.objects.create(email='mfa@torio.test', is_verified=True)
        self.secreto = servicio_mfa.generar_secreto()
        self.mfa = SegMfaUsuario.objects.create(
            usuario=self.usuario,
            metodo=METODO_TOTP,
            secreto=servicio_mfa.cifrar_secreto(self.secreto),
            activo=True,
            fecha_activacion=timezone.now(),
        )

    def _desafio(self, metodo=METODO_TOTP):
        desafio, codigo = servicio_mfa.crear_desafio(self.usuario, metodo)
        return servicio_mfa.firmar_desafio(desafio), desafio, codigo

    def _codigo_totp(self):
        return pyotp.TOTP(self.secreto).now()


class CifradoTests(MfaBaseTests):
    def test_ida_y_vuelta(self):
        cifrado = servicio_mfa.cifrar_secreto(self.secreto)
        self.assertNotIn(self.secreto, cifrado)
        self.assertEqual(servicio_mfa.descifrar_secreto(cifrado), self.secreto)

    def test_otra_clave_no_descifra(self):
        cifrado = servicio_mfa.cifrar_secreto(self.secreto)
        with override_settings(MFA_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(servicio_mfa.MfaError):
                servicio_mfa.descifrar_secreto(cifrado)


class TotpTests(MfaBaseTests):
    def test_codigo_valido(self):
        token, _, _ = self._desafio()
        verificacion = servicio_mfa.verificar_desafio(token, self._codigo_totp())
        self.assertEqual(verificacion.usuario, self.usuario)
        self.assertFalse(verificacion.uso_respaldo)

    def test_codigo_invalido(self):
        token, desafio, _ = self._desafio()
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, '000000')
        desafio.refresh_from_db()
        self.assertEqual(desafio.intentos, 1)
        self.assertFalse(desafio.consumido)

    def test_no_se_puede_reusar_el_mismo_codigo(self):
        """Anti-replay: el código sigue siendo válido en el reloj, pero su contador ya se gastó."""
        codigo = self._codigo_totp()
        token, _, _ = self._desafio()
        servicio_mfa.verificar_desafio(token, codigo)

        token_dos, _, _ = self._desafio()
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token_dos, codigo)

    def test_uri_otpauth_incluye_emisor_y_correo(self):
        uri = servicio_mfa.uri_otpauth(self.usuario, self.secreto)
        self.assertTrue(uri.startswith('otpauth://totp/'))
        self.assertIn('issuer=Torio', uri)
        self.assertIn('mfa%40torio.test', uri)


class CorreoTests(MfaBaseTests):
    def setUp(self):
        super().setUp()
        SegMfaUsuario.objects.filter(pk=self.mfa.pk).update(metodo=METODO_CORREO, secreto=None)

    def test_codigo_valido(self):
        token, _, codigo = self._desafio(METODO_CORREO)
        self.assertEqual(len(codigo), servicio_mfa.LONGITUD_CODIGO_ENVIADO)
        verificacion = servicio_mfa.verificar_desafio(token, codigo)
        self.assertEqual(verificacion.usuario, self.usuario)
        self.assertFalse(verificacion.uso_respaldo)

    def test_el_codigo_no_se_guarda_en_claro(self):
        _, desafio, codigo = self._desafio(METODO_CORREO)
        self.assertNotEqual(desafio.hash_codigo, codigo)
        self.assertEqual(len(desafio.hash_codigo), 64)

    def test_codigo_invalido(self):
        token, _, codigo = self._desafio(METODO_CORREO)
        otro = '000000' if codigo != '000000' else '111111'
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, otro)


class DesafioTests(MfaBaseTests):
    def test_no_se_consume_dos_veces(self):
        token, _, _ = self._desafio()
        servicio_mfa.verificar_desafio(token, self._codigo_totp())
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, self._codigo_totp())

    def test_expirado(self):
        token, desafio, _ = self._desafio()
        SegMfaDesafio.objects.filter(pk=desafio.pk).update(
            expira=timezone.now() - timezone.timedelta(seconds=1)
        )
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, self._codigo_totp())

    def test_bloqueo_tras_maximo_de_intentos(self):
        token, desafio, _ = self._desafio()
        for _ in range(servicio_mfa.MAX_INTENTOS):
            with self.assertRaises(servicio_mfa.MfaError):
                servicio_mfa.verificar_desafio(token, '000000')

        # Ya bloqueado: ni siquiera el código correcto lo abre.
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, self._codigo_totp())
        desafio.refresh_from_db()
        self.assertFalse(desafio.consumido)

    def test_token_manipulado(self):
        token, _, _ = self._desafio()
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token[:-1] + ('x' if token[-1] != 'x' else 'y'), '000000')

    def test_crear_desafio_limpia_los_vencidos(self):
        _, viejo, _ = self._desafio()
        SegMfaDesafio.objects.filter(pk=viejo.pk).update(
            expira=timezone.now() - timezone.timedelta(seconds=1)
        )
        self._desafio()
        self.assertFalse(SegMfaDesafio.objects.filter(pk=viejo.pk).exists())


class CodigosRespaldoTests(MfaBaseTests):
    def test_generar_reemplaza_los_anteriores(self):
        primeros = servicio_mfa.generar_codigos_respaldo(self.usuario)
        segundos = servicio_mfa.generar_codigos_respaldo(self.usuario)
        self.assertEqual(len(segundos), servicio_mfa.CANTIDAD_CODIGOS_RESPALDO)
        self.assertEqual(SegMfaCodigoRespaldo.objects.filter(usuario=self.usuario).count(),
                         servicio_mfa.CANTIDAD_CODIGOS_RESPALDO)

        token, _, _ = self._desafio()
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, primeros[0])

    def test_no_se_guardan_en_claro(self):
        codigos = servicio_mfa.generar_codigos_respaldo(self.usuario)
        guardados = SegMfaCodigoRespaldo.objects.values_list('hash_codigo', flat=True)
        self.assertNotIn(codigos[0], guardados)

    def test_sirve_como_segundo_factor_y_solo_una_vez(self):
        codigos = servicio_mfa.generar_codigos_respaldo(self.usuario)

        token, _, _ = self._desafio()
        verificacion = servicio_mfa.verificar_desafio(token, codigos[0])
        self.assertEqual(verificacion.usuario, self.usuario)
        # El motor avisa que entró con un código de respaldo: la bitácora de accesos lo
        # registra, porque significa que perdió su método habitual.
        self.assertTrue(verificacion.uso_respaldo)
        self.assertEqual(servicio_mfa.codigos_respaldo_restantes(self.usuario),
                         servicio_mfa.CANTIDAD_CODIGOS_RESPALDO - 1)

        token_dos, _, _ = self._desafio()
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token_dos, codigos[0])

    def test_se_acepta_con_guiones_y_minusculas(self):
        codigos = servicio_mfa.generar_codigos_respaldo(self.usuario)
        maquillado = f'{codigos[0][:5].lower()}-{codigos[0][5:].lower()}'
        token, _, _ = self._desafio()
        self.assertEqual(servicio_mfa.verificar_desafio(token, maquillado).usuario, self.usuario)

    def test_de_otro_usuario_no_sirve(self):
        otro = SegUsuario.objects.create(email='otro@torio.test', is_verified=True)
        codigos = servicio_mfa.generar_codigos_respaldo(otro)
        token, _, _ = self._desafio()
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, codigos[0])


class DispositivoTests(MfaBaseTests):
    def test_recordado_salta_el_segundo_paso(self):
        token = servicio_mfa.recordar_dispositivo(self.usuario, 'Firefox', '127.0.0.1')
        self.assertTrue(servicio_mfa.dispositivo_recordado(self.usuario, token))

    def test_no_se_guarda_el_token_en_claro(self):
        token = servicio_mfa.recordar_dispositivo(self.usuario)
        self.assertFalse(self.usuario.dispositivos_mfa.filter(hash_token=token).exists())

    def test_de_otro_usuario_no_sirve(self):
        token = servicio_mfa.recordar_dispositivo(self.usuario)
        otro = SegUsuario.objects.create(email='otro@torio.test', is_verified=True)
        self.assertFalse(servicio_mfa.dispositivo_recordado(otro, token))

    def test_revocado_deja_de_servir(self):
        token = servicio_mfa.recordar_dispositivo(self.usuario)
        servicio_mfa.olvidar_dispositivos(self.usuario)
        self.assertFalse(servicio_mfa.dispositivo_recordado(self.usuario, token))

    def test_vencido_deja_de_servir(self):
        token = servicio_mfa.recordar_dispositivo(self.usuario)
        self.usuario.dispositivos_mfa.update(expira=timezone.now() - timezone.timedelta(seconds=1))
        self.assertFalse(servicio_mfa.dispositivo_recordado(self.usuario, token))

    def test_token_invalido(self):
        self.assertFalse(servicio_mfa.dispositivo_recordado(self.usuario, ''))
        self.assertFalse(servicio_mfa.dispositivo_recordado(self.usuario, 'basura'))


class EstadoTests(MfaBaseTests):
    def test_mfa_activo(self):
        self.assertIsNotNone(servicio_mfa.mfa_activo(self.usuario))
        SegMfaUsuario.objects.filter(pk=self.mfa.pk).update(activo=False)
        self.assertIsNone(servicio_mfa.mfa_activo(self.usuario))


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA)
class MfaEndpointsTests(TestCase):
    """
    Los endpoints de gestión. Sin MFA previo: cada test arma el estado que necesita
    pasando por la API, que es como lo va a usar el front.
    """

    CLAVE = 'clave-de-prueba-123'

    def setUp(self):
        # El throttling usa el cache y el cache es LocMem: sin limpiarlo, los scopes se
        # arrastran entre tests del mismo proceso.
        cache.clear()
        self.usuario = SegUsuario.objects.create(email='endpoints@torio.test', is_verified=True)
        self.usuario.set_password(self.CLAVE)
        self.usuario.save()
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    def _configurar_totp(self):
        respuesta = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_TOTP})
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.data['mfa_token'], respuesta.data['secreto']

    def _activar_totp(self):
        token, secreto = self._configurar_totp()
        respuesta = self.client.post('/seguridad/mfa/activar/', {
            'mfa_token': token,
            'codigo': pyotp.TOTP(secreto).now(),
        })
        self.assertEqual(respuesta.status_code, 200)
        return secreto, respuesta.data['codigos_respaldo']

    def test_requiere_autenticacion(self):
        anonimo = APIClient()
        self.assertEqual(anonimo.get('/seguridad/mfa/').status_code, 401)
        self.assertEqual(anonimo.post('/seguridad/mfa/configurar/', {'metodo': METODO_TOTP}).status_code, 401)
        self.assertEqual(anonimo.get('/seguridad/mfa/metodos/').status_code, 401)

    def test_metodos_disponibles(self):
        """
        El front pinta el selector con esto. Se afirma el orden porque es intencional
        —primero los que no exigen instalar una app— y se perdería sin una prueba.
        """
        respuesta = self.client.get('/seguridad/mfa/metodos/')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            [metodo['codigo'] for metodo in respuesta.data],
            [METODO_CORREO, METODO_SMS, METODO_TOTP],
        )
        self.assertEqual(respuesta.data[0]['nombre'], 'Código por correo')

    def test_los_metodos_son_los_que_acepta_configurar(self):
        """
        Guarda contra la desincronización: si alguien agrega un método al selector sin
        agregarlo al enum, `configurar` lo rechazaría y el usuario vería una opción rota.
        """
        codigos = [metodo['codigo'] for metodo in self.client.get('/seguridad/mfa/metodos/').data]

        self.assertEqual(set(codigos), {codigo for codigo, _ in METODOS})

    def test_estado_sin_mfa(self):
        respuesta = self.client.get('/seguridad/mfa/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data['activo'])
        self.assertIsNone(respuesta.data['metodo'])
        self.assertEqual(respuesta.data['codigos_respaldo_restantes'], 0)

    def test_configurar_totp_devuelve_uri_y_no_activa(self):
        respuesta = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_TOTP})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data['otpauth_uri'].startswith('otpauth://totp/'))
        self.assertFalse(SegMfaUsuario.objects.get(usuario=self.usuario).activo)
        self.assertFalse(self.client.get('/seguridad/mfa/').data['activo'])

    def test_configurar_metodo_invalido(self):
        self.assertEqual(
            self.client.post('/seguridad/mfa/configurar/', {'metodo': 'paloma-mensajera'}).status_code,
            400,
        )

    def test_activar_con_codigo_valido(self):
        secreto, codigos = self._activar_totp()
        self.assertEqual(len(codigos), servicio_mfa.CANTIDAD_CODIGOS_RESPALDO)

        estado = self.client.get('/seguridad/mfa/').data
        self.assertTrue(estado['activo'])
        self.assertEqual(estado['metodo'], METODO_TOTP)
        self.assertEqual(estado['codigos_respaldo_restantes'], servicio_mfa.CANTIDAD_CODIGOS_RESPALDO)

    def test_activar_con_codigo_invalido(self):
        token, _ = self._configurar_totp()
        respuesta = self.client.post('/seguridad/mfa/activar/', {'mfa_token': token, 'codigo': '000000'})
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(SegMfaUsuario.objects.get(usuario=self.usuario).activo)

    def test_no_se_reconfigura_con_el_mfa_activo(self):
        self._activar_totp()
        respuesta = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_TOTP})
        self.assertEqual(respuesta.status_code, 400)

    def test_activar_dos_veces(self):
        secreto, _ = self._activar_totp()
        respuesta = self.client.post('/seguridad/mfa/activar/', {
            'mfa_token': 'cualquiera', 'codigo': pyotp.TOTP(secreto).now(),
        })
        self.assertEqual(respuesta.status_code, 400)

    def test_desafio_de_otro_usuario_no_sirve(self):
        """El desafío es de quien lo abrió, aunque quien lo cierre esté autenticado."""
        self._activar_totp()
        otro = SegUsuario.objects.create(email='ajeno@torio.test', is_verified=True)
        otro.set_password(self.CLAVE)
        otro.save()
        desafio, _ = servicio_mfa.crear_desafio(otro, METODO_TOTP)

        respuesta = self.client.post('/seguridad/mfa/desactivar/', {
            'password': self.CLAVE,
            'mfa_token': servicio_mfa.firmar_desafio(desafio),
            'codigo': '000000',
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertTrue(SegMfaUsuario.objects.get(usuario=self.usuario).activo)

    def test_desactivar(self):
        secreto, _ = self._activar_totp()
        token = self.client.post('/seguridad/mfa/desafio/').data['mfa_token']

        # Una ventana más adelante: el código de la activación ya gastó su contador, y
        # el anti-replay lo rechazaría. Un usuario real teclea el siguiente.
        futuro = time.time() + servicio_mfa.PERIODO_TOTP
        with patch.object(servicio_mfa.time, 'time', return_value=futuro):
            respuesta = self.client.post('/seguridad/mfa/desactivar/', {
                'password': self.CLAVE,
                'mfa_token': token,
                'codigo': pyotp.TOTP(secreto).at(futuro),
            })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(SegMfaUsuario.objects.filter(usuario=self.usuario).exists())
        self.assertEqual(SegMfaCodigoRespaldo.objects.filter(usuario=self.usuario).count(), 0)

    def test_desactivar_con_clave_incorrecta(self):
        secreto, _ = self._activar_totp()
        token = self.client.post('/seguridad/mfa/desafio/').data['mfa_token']

        respuesta = self.client.post('/seguridad/mfa/desactivar/', {
            'password': 'otra-clave',
            'mfa_token': token,
            'codigo': pyotp.TOTP(secreto).now(),
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertTrue(SegMfaUsuario.objects.get(usuario=self.usuario).activo)

    def test_desactivar_con_codigo_de_respaldo(self):
        _, codigos = self._activar_totp()
        token = self.client.post('/seguridad/mfa/desafio/').data['mfa_token']

        respuesta = self.client.post('/seguridad/mfa/desactivar/', {
            'password': self.CLAVE,
            'mfa_token': token,
            'codigo': codigos[0],
        })
        self.assertEqual(respuesta.status_code, 200)

    def test_desafio_sin_mfa_activo(self):
        self.assertEqual(self.client.post('/seguridad/mfa/desafio/').status_code, 400)

    def test_regenerar_codigos_respaldo(self):
        _, primeros = self._activar_totp()
        respuesta = self.client.post('/seguridad/mfa/codigos-respaldo/', {'password': self.CLAVE})
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotEqual(set(respuesta.data['codigos_respaldo']), set(primeros))

    def test_regenerar_codigos_respaldo_con_clave_incorrecta(self):
        self._activar_totp()
        respuesta = self.client.post('/seguridad/mfa/codigos-respaldo/', {'password': 'otra'})
        self.assertEqual(respuesta.status_code, 400)

    def test_revocar_dispositivo(self):
        self._activar_totp()
        servicio_mfa.recordar_dispositivo(self.usuario, 'Firefox', '127.0.0.1')
        dispositivo = self.usuario.dispositivos_mfa.get()

        self.assertEqual(len(self.client.get('/seguridad/mfa/').data['dispositivos']), 1)
        self.assertEqual(self.client.delete(f'/seguridad/mfa/dispositivo/{dispositivo.pk}/').status_code, 204)
        self.assertEqual(self.usuario.dispositivos_mfa.count(), 0)

    def test_no_se_revoca_el_dispositivo_de_otro(self):
        otro = SegUsuario.objects.create(email='ajeno@torio.test', is_verified=True)
        servicio_mfa.recordar_dispositivo(otro, 'Firefox', '127.0.0.1')
        ajeno = otro.dispositivos_mfa.get()

        self.assertEqual(self.client.delete(f'/seguridad/mfa/dispositivo/{ajeno.pk}/').status_code, 404)
        self.assertEqual(otro.dispositivos_mfa.count(), 1)

    def test_activar_cierra_las_demas_sesiones(self):
        with patch.object(servicio_mfa, 'invalidar_sesiones') as invalidar:
            self._activar_totp()
        invalidar.assert_called_once_with(self.usuario)


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA)
class MfaEndpointsCorreoTests(TestCase):
    def setUp(self):
        cache.clear()
        self.usuario = SegUsuario.objects.create(email='correo@torio.test', is_verified=True)
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.enviados = []

        parche = patch.object(
            servicio_mfa, 'enviar_codigo',
            side_effect=lambda usuario, codigo, metodo: self.enviados.append((usuario, codigo, metodo)),
        )
        parche.start()
        self.addCleanup(parche.stop)

    def test_configurar_envia_codigo_y_no_lo_devuelve(self):
        respuesta = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_CORREO})
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('secreto', respuesta.data)
        self.assertNotIn('otpauth_uri', respuesta.data)
        self.assertEqual(len(self.enviados), 1)
        self.assertNotIn(self.enviados[0][1], str(respuesta.data))

    def test_activar_con_el_codigo_enviado(self):
        token = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_CORREO}).data['mfa_token']
        codigo = self.enviados[0][1]

        respuesta = self.client.post('/seguridad/mfa/activar/', {'mfa_token': token, 'codigo': codigo})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.client.get('/seguridad/mfa/').data['metodo'], METODO_CORREO)


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA, TURNSTILE_ENABLED=False)
class LoginMfaTests(TestCase):
    """El login en dos pasos, visto como lo ve el front."""

    CLAVE = 'clave-de-prueba-123'

    def setUp(self):
        cache.clear()
        self.usuario = SegUsuario.objects.create(email='login@torio.test', is_verified=True)
        self.usuario.set_password(self.CLAVE)
        self.usuario.save()
        self.client = APIClient()
        self.secreto = None

    def _activar_mfa(self, metodo=METODO_TOTP):
        self.secreto = servicio_mfa.generar_secreto()
        SegMfaUsuario.objects.create(
            usuario=self.usuario,
            metodo=metodo,
            secreto=servicio_mfa.cifrar_secreto(self.secreto) if metodo == METODO_TOTP else None,
            activo=True,
            fecha_activacion=timezone.now(),
        )

    def _login(self, clave=None):
        return self.client.post('/seguridad/login/', {
            'email': self.usuario.email,
            'password': clave or self.CLAVE,
        })

    def test_login_sin_mfa_no_cambia(self):
        respuesta = self._login()
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('access_token', respuesta.cookies)
        self.assertIn('refresh_token', respuesta.cookies)
        self.assertNotIn('mfa_requerido', respuesta.data)

    def test_login_con_mfa_no_emite_tokens(self):
        self._activar_mfa()
        respuesta = self._login()

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data['mfa_requerido'])
        self.assertEqual(respuesta.data['metodo'], METODO_TOTP)
        self.assertNotIn('access_token', respuesta.cookies)
        self.assertNotIn('refresh_token', respuesta.cookies)
        # Ni siquiera el perfil: hasta el segundo paso no se sabe nada de la cuenta.
        self.assertNotIn('email', respuesta.data)

    def test_segundo_paso_emite_tokens(self):
        self._activar_mfa()
        token = self._login().data['mfa_token']

        respuesta = self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token,
            'codigo': pyotp.TOTP(self.secreto).now(),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['email'], self.usuario.email)
        self.assertTrue(respuesta.data['mfa_activo'])
        self.assertIn('access_token', respuesta.cookies)
        # Sin `recordar_dispositivo`, no se deja cookie de confianza.
        self.assertNotIn('mfa_dispositivo', respuesta.cookies)

    def test_segundo_paso_con_codigo_invalido(self):
        self._activar_mfa()
        token = self._login().data['mfa_token']

        respuesta = self.client.post('/seguridad/login/mfa/', {'mfa_token': token, 'codigo': '000000'})
        self.assertEqual(respuesta.status_code, 401)
        self.assertNotIn('access_token', respuesta.cookies)

    def test_ultimo_ingreso_se_marca_en_el_segundo_paso(self):
        """Marcar el ingreso al validar la clave contaría logins que nunca se completaron."""
        self._activar_mfa()
        self._login()
        self.usuario.refresh_from_db()
        self.assertIsNone(self.usuario.last_login)

        token = self.client.post('/seguridad/login/', {
            'email': self.usuario.email, 'password': self.CLAVE,
        }).data['mfa_token']
        self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token, 'codigo': pyotp.TOTP(self.secreto).now(),
        })
        self.usuario.refresh_from_db()
        self.assertIsNotNone(self.usuario.last_login)

    def test_recordar_dispositivo_salta_el_segundo_paso(self):
        self._activar_mfa()
        token = self._login().data['mfa_token']
        respuesta = self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token,
            'codigo': pyotp.TOTP(self.secreto).now(),
            'recordar_dispositivo': True,
        })
        self.assertIn('mfa_dispositivo', respuesta.cookies)

        # El cliente conserva la cookie: el siguiente login entra derecho.
        siguiente = self._login()
        self.assertNotIn('mfa_requerido', siguiente.data)
        self.assertEqual(siguiente.data['email'], self.usuario.email)

    def test_dispositivo_revocado_vuelve_a_pedir_codigo(self):
        self._activar_mfa()
        token = self._login().data['mfa_token']
        self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token,
            'codigo': pyotp.TOTP(self.secreto).now(),
            'recordar_dispositivo': True,
        })
        servicio_mfa.olvidar_dispositivos(self.usuario)

        self.assertTrue(self._login().data['mfa_requerido'])

    def test_no_revela_si_la_cuenta_existe(self):
        self._activar_mfa()
        inexistente = self.client.post('/seguridad/login/', {
            'email': 'nadie@torio.test', 'password': self.CLAVE,
        })
        clave_mala = self._login('clave-incorrecta')

        self.assertEqual(inexistente.status_code, 401)
        self.assertEqual(clave_mala.status_code, 401)
        self.assertEqual(inexistente.data['detail'], clave_mala.data['detail'])
        self.assertFalse(SegMfaDesafio.objects.exists())

    def test_cuenta_sin_verificar_no_abre_desafio(self):
        self._activar_mfa()
        SegUsuario.objects.filter(pk=self.usuario.pk).update(is_verified=False)
        respuesta = self._login()
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(SegMfaDesafio.objects.exists())

    def test_reenviar_codigo(self):
        self._activar_mfa(METODO_CORREO)
        enviados = []
        with patch.object(servicio_mfa, 'enviar_codigo', side_effect=lambda u, c, m: enviados.append(c)):
            token = self._login().data['mfa_token']
            self.assertEqual(len(enviados), 1)

            respuesta = self.client.post('/seguridad/login/mfa/reenviar/', {'mfa_token': token})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(len(enviados), 2)

            # El código viejo deja de servir; el nuevo entra.
            self.assertEqual(
                self.client.post('/seguridad/login/mfa/', {'mfa_token': token, 'codigo': enviados[0]}).status_code,
                401,
            )
        respuesta = self.client.post('/seguridad/login/mfa/', {'mfa_token': token, 'codigo': enviados[1]})
        self.assertEqual(respuesta.status_code, 200)

    def test_reenviar_no_reinicia_los_intentos(self):
        """Si no, pedir un correo nuevo cada cinco intentos daría intentos infinitos."""
        self._activar_mfa(METODO_CORREO)
        with patch.object(servicio_mfa, 'enviar_codigo'):
            token = self._login().data['mfa_token']
            for _ in range(servicio_mfa.MAX_INTENTOS):
                self.client.post('/seguridad/login/mfa/', {'mfa_token': token, 'codigo': '000000'})

            respuesta = self.client.post('/seguridad/login/mfa/reenviar/', {'mfa_token': token})
        self.assertEqual(respuesta.status_code, 400)


@override_settings(TURNSTILE_ENABLED=False)
class SesionTests(TestCase):
    """Duración de la sesión: inactividad (refresh) y tope absoluto."""

    CLAVE = 'clave-de-prueba-123'

    def setUp(self):
        cache.clear()
        self.usuario = SegUsuario.objects.create(email='sesion@torio.test', is_verified=True)
        self.usuario.set_password(self.CLAVE)
        self.usuario.save()
        self.client = APIClient()

    def _login(self):
        return self.client.post('/seguridad/login/', {
            'email': self.usuario.email, 'password': self.CLAVE,
        })

    def test_refresh_renueva_y_conserva_el_inicio_de_sesion(self):
        self._login()
        respuesta = self.client.post('/seguridad/refresh/')
        self.assertEqual(respuesta.status_code, 200)

        token = RefreshToken(respuesta.cookies['refresh_token'].value)
        self.assertIn('ses', token.payload)

    def test_la_sesion_caduca_al_llegar_al_tope(self):
        self._login()
        # Una rotación normal desliza el vencimiento; el tope no se mueve.
        self.client.post('/seguridad/refresh/')

        vencido = timezone.now() - settings.SESION_MAXIMA - timedelta(seconds=1)
        token = RefreshToken(self.client.cookies['refresh_token'].value)
        token['ses'] = int(vencido.timestamp())
        self.client.cookies['refresh_token'] = str(token)

        respuesta = self.client.post('/seguridad/refresh/')
        self.assertEqual(respuesta.status_code, 401)

    def test_el_inicio_no_se_corre_al_rotar(self):
        self._login()
        inicio = RefreshToken(self.client.cookies['refresh_token'].value)['ses']
        for _ in range(3):
            self.client.post('/seguridad/refresh/')
        self.assertEqual(RefreshToken(self.client.cookies['refresh_token'].value)['ses'], inicio)


class CelularTests(TestCase):
    """Se guarda E.164; Zinc exige diez dígitos pelados y solo entrega en Colombia."""

    def _celular(self, valor):
        usuario = SegUsuario(email='cel@torio.test', celular=valor)
        return servicio_mfa.celular_para_sms(usuario)

    def test_formatos_validos(self):
        for valor in (
            '+573001234567', '+57 300 123 4567', '00573001234567',
            '3001234567', '300 123 4567', '300-123-4567',
        ):
            with self.subTest(valor=valor):
                self.assertEqual(self._celular(valor), '3001234567')

    def test_formatos_invalidos(self):
        for valor in (None, '', '300123', '12345678901', 'no-es-un-numero'):
            with self.subTest(valor=valor):
                self.assertIsNone(self._celular(valor))

    def test_sin_mas_se_lee_como_nacional(self):
        """
        Sin `+` no hay forma de distinguir un indicativo del arranque del número, así
        que se asume Colombia: '57…' pelado deja catorce dígitos y no es un número.
        """
        self.assertIsNone(self._celular('573001234567'))

    def test_un_numero_extranjero_no_recibe_sms(self):
        """Válido como número, pero Zinc no entrega ahí: mejor None que un envío al vacío."""
        self.assertIsNone(self._celular('+525512345678'))


class NormalizarE164Tests(TestCase):
    """
    La validación es de *forma*, no de existencia: sin `phonenumbers` no se sabe si un
    número está asignado. Colombia es el único país con largo nacional verificado.
    """

    def test_deja_el_numero_en_e164(self):
        casos = {
            '+57 300 123 4567': '+573001234567',
            '3001234567': '+573001234567',
            '(300) 123-4567': '+573001234567',
            '00 44 7911 123456': '+447911123456',
            '+44 7911 123456': '+447911123456',
            '+1 202 555 0173': '+12025550173',
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(normalizar_e164(valor), esperado)

    def test_rechaza_lo_que_no_es_un_numero_posible(self):
        for valor in (
            None, '', '   ', 'no-es-un-numero', '+', '+0123456789',
            '+12345',                 # más corto que cualquier número del mundo
            '+1234567890123456',      # E.164 no admite más de quince dígitos
            '+57300123456',           # Colombia son diez dígitos nacionales
            '+5730012345678',
        ):
            with self.subTest(valor=valor):
                self.assertIsNone(normalizar_e164(valor))

    def test_un_pais_sin_regla_propia_pasa_con_la_validacion_generica(self):
        """Se acepta la forma; que el número exista solo lo prueba mandarle un código."""
        self.assertEqual(normalizar_e164('+4479119'), '+4479119')

    def test_a_nacional_solo_devuelve_los_del_pais(self):
        self.assertEqual(a_nacional('+573001234567'), '3001234567')
        self.assertIsNone(a_nacional('+447911123456'))


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA)
class SmsTests(MfaBaseTests):
    def setUp(self):
        super().setUp()
        SegMfaUsuario.objects.filter(pk=self.mfa.pk).update(metodo=METODO_SMS, secreto=None)
        SegUsuario.objects.filter(pk=self.usuario.pk).update(celular='+57 300 123 4567')
        self.usuario.refresh_from_db()

    def test_codigo_valido(self):
        token, _, codigo = self._desafio(METODO_SMS)
        self.assertEqual(len(codigo), servicio_mfa.LONGITUD_CODIGO_ENVIADO)
        verificacion = servicio_mfa.verificar_desafio(token, codigo)
        self.assertEqual(verificacion.usuario, self.usuario)
        self.assertFalse(verificacion.uso_respaldo)

    def test_el_codigo_no_se_guarda_en_claro(self):
        _, desafio, codigo = self._desafio(METODO_SMS)
        self.assertNotEqual(desafio.hash_codigo, codigo)

    def test_codigo_invalido(self):
        token, _, codigo = self._desafio(METODO_SMS)
        with self.assertRaises(servicio_mfa.MfaError):
            servicio_mfa.verificar_desafio(token, '000000' if codigo != '000000' else '111111')

    def test_envio_normaliza_el_numero(self):
        with patch.object(servicio_mfa, 'Zinc') as zinc:
            servicio_mfa.enviar_codigo(self.usuario, '123456', METODO_SMS)

        numero, mensaje = zinc.return_value.sms.call_args.args
        self.assertEqual(numero, '3001234567')
        self.assertIn('123456', mensaje)
        zinc.return_value.correo.assert_not_called()

    def test_envio_sin_celular_valido_no_explota(self):
        """Solo pasa si editaron el celular después de activar; le quedan los respaldos."""
        SegUsuario.objects.filter(pk=self.usuario.pk).update(celular='123')
        self.usuario.refresh_from_db()

        with patch.object(servicio_mfa, 'Zinc') as zinc:
            servicio_mfa.enviar_codigo(self.usuario, '123456', METODO_SMS)
        zinc.return_value.sms.assert_not_called()

    def test_correo_no_manda_sms(self):
        with patch.object(servicio_mfa, 'Zinc') as zinc:
            servicio_mfa.enviar_codigo(self.usuario, '123456', METODO_CORREO)
        zinc.return_value.sms.assert_not_called()
        zinc.return_value.correo.assert_called_once()


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA, TURNSTILE_ENABLED=False)
class MfaSmsEndpointsTests(TestCase):
    CLAVE = 'clave-de-prueba-123'

    def setUp(self):
        cache.clear()
        self.usuario = SegUsuario.objects.create(
            email='sms@torio.test', is_verified=True, celular='3001234567',
        )
        self.usuario.set_password(self.CLAVE)
        self.usuario.save()
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.enviados = []

        parche = patch.object(
            servicio_mfa, 'enviar_codigo',
            side_effect=lambda usuario, codigo, metodo: self.enviados.append((codigo, metodo)),
        )
        parche.start()
        self.addCleanup(parche.stop)

    def test_configurar_sin_celular_valido(self):
        # Sobre la instancia, no por queryset: `force_authenticate` guarda este mismo
        # objeto y la vista leería el valor viejo.
        self.usuario.celular = None
        self.usuario.save(update_fields=['celular'])
        respuesta = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_SMS})

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(SegMfaUsuario.objects.filter(usuario=self.usuario).exists())
        self.assertEqual(self.enviados, [])

    def test_configurar_y_activar(self):
        respuesta = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_SMS})
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('secreto', respuesta.data)
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.enviados[0][1], METODO_SMS)

        codigo, _ = self.enviados[0]
        activar = self.client.post('/seguridad/mfa/activar/', {
            'mfa_token': respuesta.data['mfa_token'], 'codigo': codigo,
        })
        self.assertEqual(activar.status_code, 200)
        self.assertEqual(self.client.get('/seguridad/mfa/').data['metodo'], METODO_SMS)

    def test_login_en_dos_pasos_por_sms(self):
        configurar = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_SMS})
        self.client.post('/seguridad/mfa/activar/', {
            'mfa_token': configurar.data['mfa_token'], 'codigo': self.enviados[0][0],
        })

        anonimo = APIClient()
        login = anonimo.post('/seguridad/login/', {'email': self.usuario.email, 'password': self.CLAVE})
        self.assertTrue(login.data['mfa_requerido'])
        self.assertEqual(login.data['metodo'], METODO_SMS)
        self.assertEqual(self.enviados[-1][1], METODO_SMS)

        segundo = anonimo.post('/seguridad/login/mfa/', {
            'mfa_token': login.data['mfa_token'], 'codigo': self.enviados[-1][0],
        })
        self.assertEqual(segundo.status_code, 200)
        self.assertIn('access_token', segundo.cookies)

    def test_reenviar_por_sms(self):
        configurar = self.client.post('/seguridad/mfa/configurar/', {'metodo': METODO_SMS})
        token = configurar.data['mfa_token']

        respuesta = self.client.post('/seguridad/login/mfa/reenviar/', {'mfa_token': token})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(self.enviados), 2)
        self.assertNotEqual(self.enviados[0][0], self.enviados[1][0])


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA)
class CambioDeCelularTests(TestCase):
    """
    Con SMS activo, el celular es parte del segundo factor: moverlo exige probarlo.
    """

    def setUp(self):
        cache.clear()
        self.usuario = SegUsuario.objects.create(
            email='cambio@torio.test', is_verified=True, celular='3001234567',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.url = f'/seguridad/usuario/{self.usuario.pk}/'

    def _activar_sms(self):
        SegMfaUsuario.objects.create(
            usuario=self.usuario, metodo=METODO_SMS, activo=True, fecha_activacion=timezone.now(),
        )

    def _paso_previo(self):
        desafio, codigo = servicio_mfa.crear_desafio(self.usuario, METODO_SMS)
        return servicio_mfa.firmar_desafio(desafio), codigo

    def test_sin_mfa_se_cambia_libremente(self):
        respuesta = self.client.patch(self.url, {'celular': '3109999999'})
        self.assertEqual(respuesta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.celular, '+573109999999')

    def test_con_sms_activo_exige_codigo(self):
        self._activar_sms()
        respuesta = self.client.patch(self.url, {'celular': '3109999999'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['codigo'], 'mfa_requerido')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.celular, '3001234567')

    def test_con_codigo_valido_se_cambia(self):
        self._activar_sms()
        token, codigo = self._paso_previo()

        respuesta = self.client.patch(self.url, {
            'celular': '3109999999', 'mfa_token': token, 'codigo': codigo,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.celular, '+573109999999')

    def test_con_codigo_invalido_no_se_cambia(self):
        self._activar_sms()
        token, codigo = self._paso_previo()

        respuesta = self.client.patch(self.url, {
            'celular': '3109999999', 'mfa_token': token,
            'codigo': '000000' if codigo != '000000' else '111111',
        })
        self.assertEqual(respuesta.status_code, 400)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.celular, '3001234567')

    def test_el_mismo_numero_con_otro_formato_no_exige_codigo(self):
        self._activar_sms()
        respuesta = self.client.patch(self.url, {'celular': '+57 300 123 4567'})
        self.assertEqual(respuesta.status_code, 200)

    def test_no_se_puede_dejar_un_numero_invalido(self):
        """Teclear mal el número dejaría al titular sin recibir códigos."""
        self._activar_sms()
        token, codigo = self._paso_previo()

        respuesta = self.client.patch(self.url, {
            'celular': '300123', 'mfa_token': token, 'codigo': codigo,
        })
        self.assertEqual(respuesta.status_code, 400)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.celular, '3001234567')

    def test_otros_campos_no_se_ven_afectados(self):
        self._activar_sms()
        respuesta = self.client.patch(self.url, {'nombre_corto': 'Nuevo nombre'})
        self.assertEqual(respuesta.status_code, 200)


@override_settings(MFA_ENCRYPTION_KEY=_CLAVE_MFA)
class RegistroDeAccesoTests(TestCase):
    """La bitácora de ingresos: qué queda escrito en cada camino del login."""

    CLAVE = 'clave-de-prueba-123'
    AGENTE = 'Mozilla/5.0 (Pruebas)'
    IP = '10.0.0.7'

    def setUp(self):
        cache.clear()
        self.usuario = SegUsuario.objects.create(email='acceso@torio.test', is_verified=True)
        self.usuario.set_password(self.CLAVE)
        self.usuario.save()
        self.client = APIClient(HTTP_USER_AGENT=self.AGENTE, REMOTE_ADDR=self.IP)
        self.secreto = None

    def _activar_mfa(self, metodo=METODO_TOTP):
        self.secreto = servicio_mfa.generar_secreto()
        SegMfaUsuario.objects.create(
            usuario=self.usuario,
            metodo=metodo,
            secreto=servicio_mfa.cifrar_secreto(self.secreto) if metodo == METODO_TOTP else None,
            activo=True,
            fecha_activacion=timezone.now(),
        )

    def _login(self, email=None, clave=None):
        return self.client.post('/seguridad/login/', {
            'email': email or self.usuario.email,
            'password': clave or self.CLAVE,
        })

    def _accesos(self):
        return list(SegAcceso.objects.order_by('id'))

    def test_ingreso_exitoso_queda_registrado(self):
        self._login()

        acceso, = self._accesos()
        self.assertEqual(acceso.resultado, RESULTADO_OK)
        self.assertEqual(acceso.usuario, self.usuario)
        self.assertEqual(acceso.email, self.usuario.email)
        self.assertEqual(acceso.ip, self.IP)
        self.assertEqual(acceso.user_agent, self.AGENTE)
        self.assertIsNone(acceso.metodo_mfa)
        self.assertFalse(acceso.dispositivo_recordado)
        self.assertFalse(acceso.codigo_respaldo)

    def test_clave_incorrecta_queda_ligada_a_la_cuenta(self):
        """El titular tiene que poder ver en su historial que alguien probó su clave."""
        self.assertEqual(self._login(clave='otra-cosa').status_code, 401)

        acceso, = self._accesos()
        self.assertEqual(acceso.resultado, RESULTADO_CLAVE)
        self.assertEqual(acceso.usuario, self.usuario)

    def test_correo_inexistente_queda_sin_usuario(self):
        self.assertEqual(self._login(email='nadie@torio.test').status_code, 401)

        acceso, = self._accesos()
        self.assertEqual(acceso.resultado, RESULTADO_CLAVE)
        self.assertIsNone(acceso.usuario)
        # Sin el correo tecleado no quedaría rastro de una enumeración de usuarios.
        self.assertEqual(acceso.email, 'nadie@torio.test')

    def test_cuenta_no_verificada(self):
        SegUsuario.objects.filter(pk=self.usuario.pk).update(is_verified=False)
        self.assertEqual(self._login().status_code, 403)

        acceso, = self._accesos()
        self.assertEqual(acceso.resultado, RESULTADO_NO_VERIFICADO)
        self.assertEqual(acceso.usuario, self.usuario)

    def test_login_con_mfa_deja_pendiente_y_despues_ok(self):
        self._activar_mfa()
        token = self._login().data['mfa_token']

        pendiente, = self._accesos()
        self.assertEqual(pendiente.resultado, RESULTADO_MFA_PENDIENTE)
        self.assertEqual(pendiente.metodo_mfa, METODO_TOTP)

        self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token, 'codigo': pyotp.TOTP(self.secreto).now(),
        })
        _, ok = self._accesos()
        self.assertEqual(ok.resultado, RESULTADO_OK)
        self.assertEqual(ok.metodo_mfa, METODO_TOTP)
        self.assertFalse(ok.codigo_respaldo)

    def test_segundo_paso_fallido_se_registra_con_la_cuenta(self):
        self._activar_mfa()
        token = self._login().data['mfa_token']

        self.assertEqual(self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token, 'codigo': '000000',
        }).status_code, 401)

        _, fallido = self._accesos()
        self.assertEqual(fallido.resultado, RESULTADO_MFA_FALLIDO)
        self.assertEqual(fallido.usuario, self.usuario)
        self.assertEqual(fallido.metodo_mfa, METODO_TOTP)

    def test_token_basura_se_registra_sin_usuario(self):
        self.assertEqual(self.client.post('/seguridad/login/mfa/', {
            'mfa_token': 'no-es-un-token', 'codigo': '000000',
        }).status_code, 401)

        fallido, = self._accesos()
        self.assertEqual(fallido.resultado, RESULTADO_MFA_FALLIDO)
        self.assertIsNone(fallido.usuario)

    def test_codigo_de_respaldo_queda_marcado(self):
        """Entrar con un respaldo significa que perdió su método: hay que poder verlo."""
        self._activar_mfa()
        codigos = servicio_mfa.generar_codigos_respaldo(self.usuario)
        token = self._login().data['mfa_token']

        self.client.post('/seguridad/login/mfa/', {'mfa_token': token, 'codigo': codigos[0]})

        _, ok = self._accesos()
        self.assertEqual(ok.resultado, RESULTADO_OK)
        self.assertTrue(ok.codigo_respaldo)

    def test_dispositivo_recordado_queda_marcado(self):
        self._activar_mfa()
        token = self._login().data['mfa_token']
        self.client.post('/seguridad/login/mfa/', {
            'mfa_token': token,
            'codigo': pyotp.TOTP(self.secreto).now(),
            'recordar_dispositivo': True,
        })
        SegAcceso.objects.all().delete()

        self._login()

        # Un solo registro: se saltó el segundo paso, así que no hay `mfa_pendiente`.
        acceso, = self._accesos()
        self.assertEqual(acceso.resultado, RESULTADO_OK)
        self.assertTrue(acceso.dispositivo_recordado)
        self.assertEqual(acceso.metodo_mfa, METODO_TOTP)

    def test_historial_solo_muestra_lo_propio(self):
        otro = SegUsuario.objects.create(email='otro@torio.test', is_verified=True)
        SegAcceso.objects.create(usuario=otro, email=otro.email, resultado=RESULTADO_OK)
        self._login()

        self.client.force_authenticate(self.usuario)
        respuesta = self.client.get('/seguridad/acceso/')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 1)
        fila = respuesta.data['results'][0]
        self.assertEqual(fila['resultado'], RESULTADO_OK)
        self.assertEqual(fila['ip'], self.IP)
        # La lista ya es de la cuenta autenticada: repetir el correo no aporta.
        self.assertNotIn('email', fila)

    def test_historial_exige_autenticacion(self):
        self.assertEqual(APIClient().get('/seguridad/acceso/').status_code, 401)


class IpDelRequestTests(TestCase):
    """
    De dónde sale la IP que queda registrada.

    Creerle a `X-Forwarded-For` sin un proxy que lo reescriba deja que cualquiera
    falsee su IP en la bitácora, así que el default es no creerle.
    """

    def _request(self):
        return RequestFactory().post(
            '/seguridad/login/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='1.2.3.4, 10.0.0.9',
        )

    @override_settings(CONFIAR_EN_PROXY=False)
    def test_sin_proxy_se_ignora_el_header(self):
        self.assertEqual(servicio_acceso.ip_del_request(self._request()), '10.0.0.1')

    @override_settings(CONFIAR_EN_PROXY=True)
    def test_con_proxy_se_toma_el_primero_de_la_cadena(self):
        self.assertEqual(servicio_acceso.ip_del_request(self._request()), '1.2.3.4')

    @override_settings(CONFIAR_EN_PROXY=True)
    def test_con_proxy_pero_sin_header_cae_en_remote_addr(self):
        peticion = RequestFactory().post('/seguridad/login/', REMOTE_ADDR='10.0.0.1')
        self.assertEqual(servicio_acceso.ip_del_request(peticion), '10.0.0.1')


class FotoDePerfilTests(TestCase):
    """
    Procesamiento y almacenamiento de la foto de perfil.

    B2 se mockea: acá se mide qué se genera, con qué ruta y qué pasa cuando algo
    falla a mitad de camino. Lo que no se puede probar sin red es que el bucket
    público sirva la URL — eso queda para verificación manual.
    """

    def setUp(self):
        self.usuario = SegUsuario.objects.create(email='foto@torio.test', is_verified=True)

    @staticmethod
    def _imagen(tamano=(600, 400), modo='RGB', formato='JPEG', color='red', exif=None):
        buffer = io.BytesIO()
        imagen = Image.new(modo, tamano, color)
        parametros = {'format': formato}
        if exif is not None:
            parametros['exif'] = exif
        imagen.save(buffer, **parametros)
        tipos = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
        return SimpleUploadedFile('perfil.jpg', buffer.getvalue(), content_type=tipos[formato])

    def test_sube_los_dos_derivados_en_webp(self):
        with patch.object(backblaze, 'subir') as subir:
            nuevo = foto.subir_foto(self._imagen(), self.usuario)

        self.assertEqual(subir.call_count, 2)
        keys = [llamada.args[1] for llamada in subir.call_args_list]
        self.assertEqual(keys, [
            f'usuarios/{self.usuario.id}/{nuevo}/original.webp',
            f'usuarios/{self.usuario.id}/{nuevo}/thumb.webp',
        ])
        for llamada in subir.call_args_list:
            self.assertEqual(llamada.args[3], 'image/webp')
            self.assertEqual(Image.open(io.BytesIO(llamada.args[2])).format, 'WEBP')

        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.imagen_uuid, nuevo)

    def test_el_thumbnail_es_cuadrado_y_el_original_respeta_proporcion(self):
        with patch.object(backblaze, 'subir') as subir:
            foto.subir_foto(self._imagen(tamano=(2000, 1000)), self.usuario)

        original, thumbnail = [Image.open(io.BytesIO(c.args[2])) for c in subir.call_args_list]
        self.assertEqual(original.size, (1024, 512))
        self.assertEqual(thumbnail.size, (320, 320))

    def test_cambiar_la_foto_estrena_url_y_borra_la_anterior(self):
        """
        El motivo del uuid: con ruta fija, el navegador seguiría mostrando la
        imagen vieja porque la URL no cambió.
        """
        with patch.object(backblaze, 'subir'):
            primero = foto.subir_foto(self._imagen(), self.usuario)
        with patch.object(backblaze, 'subir'), patch.object(backblaze, 'eliminar') as eliminar:
            segundo = foto.subir_foto(self._imagen(), self.usuario)

        self.assertNotEqual(primero, segundo)
        self.assertNotEqual(
            foto.key_original(self.usuario.id, primero),
            foto.key_original(self.usuario.id, segundo),
        )
        borradas = sorted(llamada.args[1] for llamada in eliminar.call_args_list)
        self.assertEqual(borradas, sorted([
            f'usuarios/{self.usuario.id}/{primero}/original.webp',
            f'usuarios/{self.usuario.id}/{primero}/thumb.webp',
        ]))

    def test_si_falla_el_thumbnail_no_queda_media_foto(self):
        """Foto nueva con miniatura vieja es la inconsistencia más visible."""
        with patch.object(backblaze, 'subir'):
            original = foto.subir_foto(self._imagen(), self.usuario)

        corte = ConnectionClosedError(endpoint_url='https://s3.us-east-005.backblazeb2.com/x')
        with patch.object(backblaze, 'subir', side_effect=[None, corte]), \
             patch.object(backblaze, 'eliminar') as eliminar:
            with self.assertRaises(ConnectionClosedError):
                foto.subir_foto(self._imagen(), self.usuario)

        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.imagen_uuid, original, 'la foto vieja tiene que seguir vigente')
        self.assertEqual(eliminar.call_count, 2, 'hay que limpiar el original que sí subió')

    def test_no_toca_b2_si_la_imagen_no_sirve(self):
        casos = {
            'tipo no permitido': SimpleUploadedFile('a.gif', b'GIF89a', content_type='image/gif'),
            'contenido que no es imagen': SimpleUploadedFile(
                'a.jpg', b'no soy una imagen', content_type='image/jpeg',
            ),
            'png disfrazado de jpeg': SimpleUploadedFile(
                'a.jpg', self._imagen(formato='PNG').read(), content_type='image/jpeg',
            ),
        }
        for nombre, archivo in casos.items():
            with self.subTest(caso=nombre):
                with patch.object(backblaze, 'subir') as subir:
                    with self.assertRaises(ValueError):
                        foto.subir_foto(archivo, self.usuario)
                subir.assert_not_called()

    def test_rechaza_la_bomba_de_descompresion(self):
        """
        Un PNG de menos de 1 MB puede pedir cientos de MB de RAM al decodificarse:
        el límite de bytes no protege de eso.
        """
        grande = self._imagen(tamano=(8000, 8000), formato='PNG', color='white')
        self.assertLess(grande.size, imagenes.TAMANO_MAXIMO, 'el caso pierde sentido si no pasa el límite de peso')

        with patch.object(backblaze, 'subir') as subir:
            with self.assertRaises(ValueError) as c:
                foto.subir_foto(grande, self.usuario)
        self.assertIn('megapíxeles', str(c.exception))
        subir.assert_not_called()

    def test_corrige_la_orientacion_de_las_fotos_de_celular(self):
        exif = Image.Exif()
        exif[274] = 6  # rotar 90°
        apaisada = self._imagen(tamano=(600, 200), exif=exif)

        with patch.object(backblaze, 'subir') as subir:
            foto.subir_foto(apaisada, self.usuario)

        original = Image.open(io.BytesIO(subir.call_args_list[0].args[2]))
        self.assertGreater(original.height, original.width, 'la foto se sirvió rotada')

    def test_la_transparencia_se_compone_sobre_blanco(self):
        """Descartar el alfa sin componer deja a la vista los bytes de abajo, casi siempre negros."""
        transparente = self._imagen(modo='RGBA', formato='PNG', color=(0, 0, 0, 0))

        with patch.object(backblaze, 'subir') as subir:
            foto.subir_foto(transparente, self.usuario)

        original = Image.open(io.BytesIO(subir.call_args_list[0].args[2])).convert('RGB')
        self.assertEqual(original.getpixel((5, 5)), (255, 255, 255))

    def test_sin_foto_el_serializer_no_inventa_una_url(self):
        datos = SegUsuarioMeSerializer(self.usuario).data
        self.assertIsNone(datos['imagen'])
        self.assertIsNone(datos['imagen_thumbnail'])

    def test_con_foto_el_serializer_arma_las_dos_urls(self):
        with patch.object(backblaze, 'subir'):
            nuevo = foto.subir_foto(self._imagen(), self.usuario)

        datos = SegUsuarioMeSerializer(self.usuario).data
        base = settings.B2_CDN_URL_PUBLICO.rstrip('/')
        self.assertEqual(datos['imagen'], f'{base}/usuarios/{self.usuario.id}/{nuevo}/original.webp')
        self.assertEqual(datos['imagen_thumbnail'], f'{base}/usuarios/{self.usuario.id}/{nuevo}/thumb.webp')
