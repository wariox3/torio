"""
La cuenta de la plataforma vista desde afuera: cómo se muestra en los contenedores
y cómo se elimina.

Ningún modelo de un contenedor apunta con FK a `SegUsuario`: guardan el correo de
quien hizo algo como texto (`GenDocumento.usuario`, `ConMovimiento.usuario`,
`VenTurno.usuario`). Así eliminar una cuenta no toca los documentos ni los libros
de ninguna empresa, y el borrado solo resuelve dependencias del schema público.
"""

from django.db import transaction

from contenedor.models import CtnCliente
from seguridad import foto
from seguridad import mfa as servicio_mfa
from seguridad.models import SegUsuario, SegUsuarioCliente


def nombre_de_usuario(email):
    """
    Cómo mostrar a quien hizo algo en un contenedor, que guarda solo su correo.

    El `nombre_corto` de la cuenta si todavía existe; si se eliminó, el correo.
    """
    if not email:
        return ''
    nombre = SegUsuario.objects.filter(email=email).values_list('nombre_corto', flat=True).first()
    return (nombre or '').strip() or email


def eliminar_cuenta(usuario) -> None:
    """
    Borra la cuenta. Quien llama ya validó que no es propietaria de ningún
    contenedor.

    Lo que cuelga de ella en el público lo resuelve el `on_delete` de cada FK: se
    van el segundo factor, las invitaciones y las membresías; quedan sin autor la
    bitácora de accesos, las solicitudes, los pagos y los contactos de facturación.

    Lanza `ProtectedError` si algo protegido todavía la referencia (una
    suscripción de un contenedor que no es suyo).
    """
    usuario_id = usuario.pk
    imagen_uuid = usuario.imagen_uuid

    with transaction.atomic():
        # En un contenedor `listo` se sale con `remove_user`, que borra también su
        # `UserTenantPermissions` dentro del schema: el CASCADE solo alcanza la fila
        # del público. Uno que no está `listo` puede no tener tablas.
        membresias = SegUsuarioCliente.objects.filter(usuario=usuario).select_related('cliente')
        for membresia in membresias:
            if membresia.cliente.estado == CtnCliente.ESTADO_LISTO:
                membresia.cliente.remove_user(usuario)

        # Antes del borrado, que deja los tokens sin usuario (SET_NULL): un refresh
        # robado no debe poder emitir más access tokens.
        servicio_mfa.invalidar_sesiones(usuario)

        # `force_drop`: django-tenant-users prohíbe el `delete()` común y manda a
        # usar su `delete_user()`, que solo desactiva y a un propietario le borra
        # los contenedores.
        usuario.delete(force_drop=True)

        # B2 no es transaccional: la foto se borra solo si el COMMIT pasó.
        if imagen_uuid:
            transaction.on_commit(lambda: foto.borrar_foto(usuario_id, imagen_uuid))
