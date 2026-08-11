"""
Bitácora de ingresos.

Módulo de servicio al estilo de `seguridad/mfa.py`: las vistas dicen qué pasó y acá se
arma la fila. Escribe `SegAcceso` en el schema público, en los dos pasos del login.

No hay `try/except` alrededor del insert a propósito: si no se puede escribir la
auditoría es porque la base no responde, y entonces el login tampoco iba a funcionar.
Tragarse el error dejaría ingresos sin registrar justo cuando algo anda mal.
"""

from django.conf import settings

from seguridad.models import SegAcceso

# El user agent llega del cliente y no tiene tope; se corta antes de guardarlo para que
# nadie use el campo como buzón de escritura arbitraria.
MAX_USER_AGENT = 500


def ip_del_request(request) -> str | None:
    """
    IP del cliente.

    `REMOTE_ADDR` detrás de nginx o Cloudflare es la del proxy, no la del usuario, y
    entonces toda la bitácora apunta al mismo lado. `X-Forwarded-For` da la real, pero
    solo se puede creer si hay un proxy que lo reescriba: expuesto directo, cualquiera
    manda el header que quiera y falsea su IP. Por eso `CONFIAR_EN_PROXY` arranca
    apagado y se prende en el despliegue que sí tiene proxy adelante.
    """
    if request is None:
        return None

    if settings.CONFIAR_EN_PROXY:
        reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if reenviada:
            # El primero de la lista es el cliente; los siguientes son los saltos.
            return reenviada.split(',')[0].strip() or None

    return request.META.get('REMOTE_ADDR')


def agente_del_request(request) -> str | None:
    if request is None:
        return None
    agente = request.META.get('HTTP_USER_AGENT')
    return agente[:MAX_USER_AGENT] if agente else None


def registrar_acceso(
    request,
    resultado: str,
    *,
    usuario=None,
    email: str = None,
    metodo_mfa: str = None,
    dispositivo_recordado: bool = False,
    codigo_respaldo: bool = False,
) -> SegAcceso:
    """
    Deja una fila por intento de ingreso.

    `email` es el correo tecleado. Cuando no viene, se toma el del usuario: en el
    segundo paso el cliente ya no manda el correo, solo el `mfa_token`.
    """
    return SegAcceso.objects.create(
        usuario=usuario,
        email=(email or (usuario.email if usuario else ''))[:254],
        resultado=resultado,
        ip=ip_del_request(request),
        user_agent=agente_del_request(request),
        metodo_mfa=metodo_mfa,
        dispositivo_recordado=dispositivo_recordado,
        codigo_respaldo=codigo_respaldo,
    )
