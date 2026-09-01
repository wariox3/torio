"""
Motor del segundo factor: secretos, códigos, desafíos y dispositivos recordados.

Las vistas no deberían saber de `pyotp`, de Fernet ni de cómo se hashea un código:
acá se concentra esa mecánica y ellas solo traducen `MfaError` a una respuesta HTTP.

El diseño y el porqué de cada decisión están en `docs/mfa.md`.
"""

import hashlib
import hmac
import logging
import secrets
import time
from datetime import timedelta
from typing import NamedTuple

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from seguridad.models import (
    METODO_CORREO,
    METODO_SMS,
    METODO_TOTP,
    METODOS_ENVIADOS,
    SegMfaCodigoRespaldo,
    SegMfaDesafio,
    SegMfaDispositivo,
    SegMfaUsuario,
)
from utilidades.telefono import a_nacional
from utilidades.zinc import Zinc

logger = logging.getLogger(__name__)

# Nombre que ven los usuarios en la app autenticadora.
EMISOR = 'Torio'

# El desafío vive 5 minutos: suficiente para abrir el correo, corto para que una
# ventana olvidada no quede utilizable.
DURACION_DESAFIO = timedelta(minutes=5)
# Freno real a la fuerza bruta sobre 6 dígitos. El throttle de DRF no sirve para esto
# mientras el cache sea LocMemCache (un contador por worker); el conteo va en la fila.
MAX_INTENTOS = 5

# ±1 ventana de 30 s para tolerar el desfase de reloj de los celulares.
VENTANA_TOTP = 1
PERIODO_TOTP = 30

LONGITUD_CODIGO_ENVIADO = 6

CANTIDAD_CODIGOS_RESPALDO = 10
LONGITUD_CODIGO_RESPALDO = 10
# Base32 sin 0/1/8/9 ni vocales problemáticas: 32 símbolos, 10 caracteres ≈ 50 bits.
ALFABETO_RESPALDO = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'

DURACION_DISPOSITIVO = timedelta(days=30)

_SALT_DESAFIO = 'seg-mfa-desafio'
_SALT_DISPOSITIVO = 'seg-mfa-dispositivo'


class MfaError(Exception):
    """
    Error con mensaje ya redactado para el usuario final.

    Las vistas lo devuelven tal cual en `detail`; por eso ningún mensaje distingue
    entre "código incorrecto" y "desafío de otro usuario".
    """


# --------------------------------------------------------------------------- #
# Cifrado del secreto
# --------------------------------------------------------------------------- #

def _fernet():
    if not settings.MFA_ENCRYPTION_KEY:
        raise ImproperlyConfigured(
            'MFA_ENCRYPTION_KEY no está configurada. Generarla con: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(settings.MFA_ENCRYPTION_KEY.encode())


def cifrar_secreto(secreto: str) -> str:
    return _fernet().encrypt(secreto.encode()).decode()


def descifrar_secreto(secreto_cifrado: str) -> str:
    try:
        return _fernet().decrypt(secreto_cifrado.encode()).decode()
    except InvalidToken:
        # Pasa si se rotó MFA_ENCRYPTION_KEY sin migrar los secretos. No es culpa del
        # usuario, pero para él el efecto es el mismo: su app ya no le sirve.
        raise MfaError('No se pudo leer la configuración de tu segundo factor. Contacta a soporte.')


def _hash(valor: str) -> str:
    """
    HMAC-SHA256 con la clave del MFA, no SHA-256 pelado.

    Para los códigos de respaldo daría igual (50 bits de entropía), pero el código de
    6 dígitos que se manda por correo o SMS tiene solo un millón de posibilidades: con
    un hash sin clave, un dump de la base bastaría para revertirlo al instante.
    """
    clave = (settings.MFA_ENCRYPTION_KEY or settings.SECRET_KEY).encode()
    return hmac.new(clave, valor.encode(), hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# TOTP
# --------------------------------------------------------------------------- #

def generar_secreto() -> str:
    return pyotp.random_base32()


def uri_otpauth(usuario, secreto: str) -> str:
    """
    URI `otpauth://` que Angular convierte en QR. El backend no genera la imagen: menos
    dependencias, y el secreto no viaja como PNG.
    """
    return pyotp.TOTP(secreto).provisioning_uri(name=usuario.email, issuer_name=EMISOR)


def _verificar_totp(mfa: SegMfaUsuario, codigo: str) -> bool:
    """
    Valida el código y consume el contador que lo generó.

    `pyotp.TOTP.verify(valid_window=1)` no dice cuál de las tres ventanas coincidió, y
    sin ese dato no se puede impedir el replay: quien intercepte el código lo podría
    reusar durante los 90 s en que sigue siendo válido. Por eso se recorren las
    ventanas a mano y se guarda el contador en `ultimo_contador`.
    """
    if not mfa.secreto:
        return False

    totp = pyotp.TOTP(descifrar_secreto(mfa.secreto))
    contador_actual = int(time.time()) // PERIODO_TOTP

    for delta in range(-VENTANA_TOTP, VENTANA_TOTP + 1):
        contador = contador_actual + delta
        if not hmac.compare_digest(totp.generate_otp(contador), codigo):
            continue
        if mfa.ultimo_contador is not None and contador <= mfa.ultimo_contador:
            return False
        mfa.ultimo_contador = contador
        mfa.save(update_fields=['ultimo_contador'])
        return True

    return False


# --------------------------------------------------------------------------- #
# Código enviado (correo y SMS)
# --------------------------------------------------------------------------- #

def generar_codigo_enviado() -> str:
    return f'{secrets.randbelow(10 ** LONGITUD_CODIGO_ENVIADO):0{LONGITUD_CODIGO_ENVIADO}d}'


def celular_para_sms(usuario) -> str | None:
    """
    Deja el celular como lo exige Zinc: diez dígitos, sin indicativo ni separadores.

    Devuelve None cuando a esa cuenta no se le puede mandar un SMS: o el número no es
    válido, o es de otro país. Zinc solo entrega en Colombia, así que un `+52` es
    tan inservible para esto como un número mal escrito.
    """
    return a_nacional(usuario.celular)


# --------------------------------------------------------------------------- #
# Códigos de respaldo
# --------------------------------------------------------------------------- #

def _normalizar_respaldo(codigo: str) -> str:
    return codigo.strip().upper().replace('-', '').replace(' ', '')


def generar_codigos_respaldo(usuario) -> list[str]:
    """
    Reemplaza los códigos anteriores y devuelve los nuevos en claro.

    Es la única vez que existen legibles: en base solo queda el hash. Si el usuario los
    pierde, se regeneran desde el perfil (con clave), y si además perdió el segundo
    factor, el desbloqueo es manual.
    """
    codigos = [
        ''.join(secrets.choice(ALFABETO_RESPALDO) for _ in range(LONGITUD_CODIGO_RESPALDO))
        for _ in range(CANTIDAD_CODIGOS_RESPALDO)
    ]
    with transaction.atomic():
        SegMfaCodigoRespaldo.objects.filter(usuario=usuario).delete()
        SegMfaCodigoRespaldo.objects.bulk_create([
            SegMfaCodigoRespaldo(usuario=usuario, hash_codigo=_hash(c)) for c in codigos
        ])
    return codigos


def _consumir_codigo_respaldo(usuario, codigo: str) -> bool:
    actualizados = SegMfaCodigoRespaldo.objects.filter(
        usuario=usuario,
        hash_codigo=_hash(_normalizar_respaldo(codigo)),
        usado_en__isnull=True,
    ).update(usado_en=timezone.now())
    return actualizados > 0


def codigos_respaldo_restantes(usuario) -> int:
    return SegMfaCodigoRespaldo.objects.filter(usuario=usuario, usado_en__isnull=True).count()


# --------------------------------------------------------------------------- #
# Desafíos
# --------------------------------------------------------------------------- #

def crear_desafio(usuario, metodo: str, ip: str = None) -> tuple[SegMfaDesafio, str | None]:
    """
    Abre el segundo paso de un login cuya clave ya fue validada.

    Devuelve el desafío y, en los métodos enviados (correo y SMS), el código en claro
    para que la vista lo despache con Zinc. En TOTP el segundo valor es None: el código
    no se guarda ni se transmite, se recalcula del secreto.
    """
    SegMfaDesafio.objects.filter(expira__lt=timezone.now()).delete()

    codigo = generar_codigo_enviado() if metodo in METODOS_ENVIADOS else None
    desafio = SegMfaDesafio.objects.create(
        usuario=usuario,
        metodo=metodo,
        hash_codigo=_hash(codigo) if codigo else None,
        expira=timezone.now() + DURACION_DESAFIO,
        ip=ip,
    )
    return desafio, codigo


def reenviar_codigo(mfa_token: str):
    """
    Genera y manda un código nuevo para un desafío de correo o SMS en curso.

    No toca `intentos` ni `expira`: si el reenvío reiniciara el contador, bastaría con
    pedir un correo nuevo cada cinco intentos para tener intentos infinitos. El tope
    del reenvío en sí lo pone el throttle `mfa_envio_codigo`.
    """
    with transaction.atomic():
        desafio = _cargar_desafio(mfa_token)

        if desafio.consumido or desafio.expira <= timezone.now():
            raise MfaError('La sesión de verificación expiró. Inicia sesión de nuevo.')
        if desafio.metodo not in METODOS_ENVIADOS:
            raise MfaError('Este método no usa códigos enviados.')
        if desafio.intentos >= MAX_INTENTOS:
            raise MfaError('Demasiados intentos fallidos. Inicia sesión de nuevo.')

        codigo = generar_codigo_enviado()
        desafio.hash_codigo = _hash(codigo)
        desafio.save(update_fields=['hash_codigo'])

    enviar_codigo(desafio.usuario, codigo, desafio.metodo)


def firmar_desafio(desafio: SegMfaDesafio) -> str:
    """
    Token opaco que viaja al cliente entre los dos pasos del login.

    Es el UUID firmado: la firma evita que alguien enumere desafíos ajenos, y el
    consumo único y el conteo de intentos los da la fila en base.
    """
    return signing.dumps(str(desafio.id), salt=_SALT_DESAFIO)


def consultar_desafio(mfa_token: str) -> SegMfaDesafio | None:
    """
    Lee el desafío de un token sin consumirlo ni contar intentos.

    Es solo para la bitácora de accesos, que necesita a quién ligar un segundo paso
    fallido. **No sirve para decidir nada de autenticación**: no valida vencimiento ni
    consumo. Devuelve None si el token es basura o el desafío ya no está.
    """
    try:
        desafio_id = signing.loads(
            mfa_token, salt=_SALT_DESAFIO, max_age=int(DURACION_DESAFIO.total_seconds())
        )
        return SegMfaDesafio.objects.filter(pk=desafio_id).first()
    except (signing.BadSignature, ValidationError, ValueError):
        return None


def _cargar_desafio(mfa_token: str) -> SegMfaDesafio:
    max_age = int(DURACION_DESAFIO.total_seconds())
    try:
        desafio_id = signing.loads(mfa_token, salt=_SALT_DESAFIO, max_age=max_age)
    except signing.BadSignature:
        raise MfaError('La sesión de verificación expiró. Inicia sesión de nuevo.')

    try:
        return SegMfaDesafio.objects.select_for_update().get(pk=desafio_id)
    except (SegMfaDesafio.DoesNotExist, ValidationError, ValueError):
        raise MfaError('La sesión de verificación expiró. Inicia sesión de nuevo.')


class ResultadoVerificacion(NamedTuple):
    """
    Quién quedó autenticado y con qué.

    `uso_respaldo` sale hasta la vista porque queda en la bitácora de accesos: entrar
    con un código de respaldo significa que el usuario perdió su método habitual, y eso
    es a la vez soporte que se viene y una señal si no fue él.
    """

    usuario: object
    uso_respaldo: bool


def verificar_desafio(mfa_token: str, codigo: str, permitir_respaldo: bool = True) -> ResultadoVerificacion:
    """
    Resuelve el segundo paso y devuelve el usuario autenticado.

    La fila se bloquea con `select_for_update` durante toda la verificación: sin eso,
    varias peticiones en paralelo compartirían el mismo contador de intentos y el tope
    de `MAX_INTENTOS` sería sorteable lanzándolas todas a la vez.

    Ojo con la estructura: el intento fallido se registra **dentro** de la transacción
    y el `MfaError` se lanza **fuera**. Si se lanzara adentro, el rollback se llevaría
    el incremento de `intentos` y el tope no contaría nada — que es justamente lo que
    hay que evitar en el único punto donde se puede probar un código de 6 dígitos.

    Lanza `MfaError` en cualquier otro caso.
    """
    with transaction.atomic():
        desafio = _cargar_desafio(mfa_token)

        # Estos caminos no escriben nada, así que pueden lanzar desde adentro.
        if desafio.consumido or desafio.expira <= timezone.now():
            raise MfaError('La sesión de verificación expiró. Inicia sesión de nuevo.')

        if desafio.intentos >= MAX_INTENTOS:
            raise MfaError('Demasiados intentos fallidos. Inicia sesión de nuevo.')

        codigo = (codigo or '').strip()

        if desafio.metodo in METODOS_ENVIADOS:
            valido = bool(desafio.hash_codigo) and hmac.compare_digest(desafio.hash_codigo, _hash(codigo))
        else:
            # Se bloquea también la configuración: `ultimo_contador` es un recurso
            # compartido entre peticiones simultáneas del mismo usuario.
            mfa = SegMfaUsuario.objects.select_for_update().filter(usuario=desafio.usuario_id).first()
            valido = bool(mfa) and _verificar_totp(mfa, codigo)

        # El código de respaldo sirve con cualquier método: es justamente la salida para
        # cuando el habitual no está disponible. No al enrolar (`permitir_respaldo=False`):
        # ahí se está probando que el nuevo factor funciona, y un código viejo no lo prueba.
        uso_respaldo = False
        if not valido and permitir_respaldo:
            uso_respaldo = _consumir_codigo_respaldo(desafio.usuario, codigo)
            valido = uso_respaldo

        if valido:
            desafio.consumido = True
            desafio.save(update_fields=['consumido'])
            return ResultadoVerificacion(desafio.usuario, uso_respaldo)

        desafio.intentos += 1
        desafio.save(update_fields=['intentos'])
        restantes = MAX_INTENTOS - desafio.intentos

    if restantes <= 0:
        raise MfaError('Demasiados intentos fallidos. Inicia sesión de nuevo.')
    raise MfaError(f'Código incorrecto. Te quedan {restantes} intentos.')


# --------------------------------------------------------------------------- #
# Dispositivos recordados
# --------------------------------------------------------------------------- #

def recordar_dispositivo(usuario, user_agent: str = None, ip: str = None) -> str:
    """
    Registra el navegador y devuelve el token firmado para la cookie.

    En base solo queda el hash del token: un dump no permite fabricar cookies válidas.
    """
    token = secrets.token_urlsafe(32)
    SegMfaDispositivo.objects.filter(expira__lt=timezone.now()).delete()
    SegMfaDispositivo.objects.create(
        usuario=usuario,
        hash_token=_hash(token),
        user_agent=(user_agent or '')[:500] or None,
        ip=ip,
        ultimo_uso=timezone.now(),
        expira=timezone.now() + DURACION_DISPOSITIVO,
    )
    return signing.dumps(token, salt=_SALT_DISPOSITIVO)


def dispositivo_recordado(usuario, token_firmado: str) -> bool:
    """
    ¿Este navegador puede saltarse el segundo paso?

    El dispositivo se valida contra el usuario que ya probó su clave, así que una
    cookie de otra cuenta no sirve.
    """
    if not token_firmado:
        return False

    max_age = int(DURACION_DISPOSITIVO.total_seconds())
    try:
        token = signing.loads(token_firmado, salt=_SALT_DISPOSITIVO, max_age=max_age)
    except signing.BadSignature:
        return False

    actualizados = SegMfaDispositivo.objects.filter(
        usuario=usuario,
        hash_token=_hash(token),
        expira__gt=timezone.now(),
    ).update(ultimo_uso=timezone.now())
    return actualizados > 0


# --------------------------------------------------------------------------- #
# Estado de la cuenta
# --------------------------------------------------------------------------- #

def mfa_activo(usuario) -> SegMfaUsuario | None:
    """Devuelve la configuración si el usuario tiene el segundo factor prendido."""
    mfa = SegMfaUsuario.objects.filter(usuario=usuario, activo=True).first()
    return mfa


def olvidar_dispositivos(usuario):
    """
    Se llama al activar o desactivar el MFA y al cambiar la clave: cualquier cambio en
    cómo se protege la cuenta invalida las excepciones concedidas antes.
    """
    SegMfaDispositivo.objects.filter(usuario=usuario).delete()


def invalidar_sesiones(usuario):
    """
    Blacklistea los refresh tokens vivos del usuario.

    Si alguien ya estaba adentro con la clave robada, prender el segundo factor tiene
    que echarlo; si no, el MFA solo protegería los logins futuros. El access token en
    curso sigue sirviendo hasta que expire (15 min), que es el precio de no consultar
    la blacklist en cada petición.
    """
    for token in OutstandingToken.objects.filter(user=usuario):
        BlacklistedToken.objects.get_or_create(token=token)


def enviar_codigo(usuario, codigo: str, metodo: str):
    """
    Manda el código por donde corresponda al método.

    No propaga fallos de Zinc: el desafío ya existe y el usuario puede pedir un reenvío
    o usar un código de respaldo, así que tumbar la petición no ayudaría en nada.
    """
    minutos = int(DURACION_DESAFIO.total_seconds() // 60)

    if metodo == METODO_SMS:
        numero = celular_para_sms(usuario)
        if not numero:
            # Solo debería pasar si el usuario editó su celular después de activar el
            # SMS. Le quedan los códigos de respaldo.
            logger.warning('MFA por SMS sin celular válido para el usuario %s', usuario.pk)
            return
        try:
            Zinc().sms(numero, f'Torio: tu codigo de verificacion es {codigo}. Vence en {minutos} minutos.')
        except Exception as e:
            logger.warning('No se pudo enviar el SMS MFA al usuario %s: %s', usuario.pk, e)
        return

    contenido = (
        f'<h1>Tu código de verificación</h1>'
        f'<p>Ingresa este código para continuar. Vence en {minutos} minutos.</p>'
        f'<p style="font-size:28px;letter-spacing:6px;"><b>{codigo}</b></p>'
        f'<p>Si no intentaste iniciar sesión, cambia tu clave.</p>'
    )
    try:
        Zinc().correo(usuario.email, 'Código de verificación', contenido)
    except Exception as e:
        logger.warning('No se pudo enviar el código MFA a %s: %s', usuario.email, e)
