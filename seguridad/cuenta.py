"""
Eliminar una cuenta por completo: la fila de `SegUsuario`, todo lo que cuelga de
ella en el schema público y su foto en B2.

No sirve `usuario.delete(force_drop=True)`: el Collector de Django recorre TODOS
los modelos con FK a `SegUsuario`, incluidos los de los contenedores
(`GenDocumento`, `ConMovimiento`, `VenTurno`), y desde el schema público esas
tablas no existen (`no existe la relación «gen_documento»`). Por eso acá cada
dependencia pública se resuelve a mano y la fila se borra con SQL.

Si aparece un FK nuevo hacia `seg_usuario` y nadie lo agrega acá, no queda un
huérfano: la restricción de la base rechaza el borrado al hacer COMMIT
(`IntegrityError`), y la vista lo convierte en un 409.
"""

from django.contrib.admin.models import LogEntry
from django.db import connection, transaction
from django_tenants.utils import schema_context
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from tenant_users.permissions.models import UserTenantPermissions

from contenedor.models import CtnCliente, CtnInvitacion, CtnSolicitud
from seguridad import foto
from seguridad import mfa as servicio_mfa
from seguridad.models import (
    SegAcceso,
    SegMfaCodigoRespaldo,
    SegMfaDesafio,
    SegMfaDispositivo,
    SegMfaUsuario,
    SegUsuario,
    SegUsuarioCliente,
)


def contenedores_con_registros(usuario) -> list[str]:
    """
    Nombres de los contenedores donde el usuario dejó registros que no se pueden
    perder ni quedar sin autor: documentos, movimientos contables o turnos de caja.

    Solo mira los contenedores `listo` donde todavía es miembro. Si dejó registros
    en uno del que ya salió, lo ataja la restricción de la base al borrar.
    """
    from contabilidad.models import ConMovimiento
    from general.models import GenDocumento
    from venta.models import VenTurno

    nombres = []
    clientes = CtnCliente.objects.filter(
        pk__in=SegUsuarioCliente.objects.filter(usuario=usuario).values('cliente_id'),
        estado=CtnCliente.ESTADO_LISTO,
    ).order_by('nombre')
    for cliente in clientes:
        with schema_context(cliente.schema_name):
            if (
                GenDocumento.objects.filter(usuario=usuario).exists()
                or ConMovimiento.objects.filter(usuario=usuario).exists()
                or VenTurno.objects.filter(usuario=usuario).exists()
            ):
                nombres.append(cliente.nombre)
    return nombres


def eliminar_cuenta(usuario) -> None:
    """
    Borra la cuenta. Quien llama ya validó que no es propietaria de ningún
    contenedor ni tiene registros en ellos.

    Lanza `IntegrityError` si la base encuentra todavía algo apuntando a la cuenta.
    """
    usuario_id = usuario.pk
    imagen_uuid = usuario.imagen_uuid

    with transaction.atomic():
        # Membresías: en un contenedor `listo` se sale con `remove_user`, que borra
        # también su `UserTenantPermissions` dentro del schema. Uno que no está
        # `listo` puede no tener tablas, así que basta con la fila pública.
        membresias = SegUsuarioCliente.objects.filter(usuario=usuario).select_related('cliente')
        for membresia in membresias:
            if membresia.cliente.estado == CtnCliente.ESTADO_LISTO:
                membresia.cliente.remove_user(usuario)
            else:
                membresia.delete()

        # Lo que se va con la cuenta.
        UserTenantPermissions.objects.filter(profile=usuario).delete()  # la del schema público
        SegMfaCodigoRespaldo.objects.filter(usuario=usuario).delete()
        SegMfaDesafio.objects.filter(usuario=usuario).delete()
        SegMfaDispositivo.objects.filter(usuario=usuario).delete()
        SegMfaUsuario.objects.filter(usuario=usuario).delete()
        CtnInvitacion.objects.filter(usuario=usuario).delete()
        CtnInvitacion.objects.filter(usuario_invitado=usuario).delete()
        LogEntry.objects.filter(user=usuario).delete()

        # Lo que se queda, sin autor: la bitácora de accesos (guarda el email que se
        # tecleó) y las solicitudes, que son del contenedor y no de la persona.
        SegAcceso.objects.filter(usuario=usuario).update(usuario=None)
        CtnSolicitud.objects.filter(usuario=usuario).update(usuario=None)
        CtnSolicitud.objects.filter(usuario_gestion=usuario).update(usuario_gestion=None)
        CtnCliente.objects.filter(owner=usuario).update(owner=None)

        # Las sesiones se blacklistean antes de soltar el token de la cuenta: un
        # refresh robado no debe poder emitir más access tokens.
        servicio_mfa.invalidar_sesiones(usuario)
        OutstandingToken.objects.filter(user=usuario).update(user=None)

        with connection.cursor() as cursor:
            cursor.execute(
                f'DELETE FROM {connection.ops.quote_name(SegUsuario._meta.db_table)} WHERE id = %s',
                [usuario_id],
            )

        # B2 no es transaccional: la foto se borra solo si el COMMIT pasó.
        if imagen_uuid:
            transaction.on_commit(
                lambda: foto.borrar_foto(usuario_id, imagen_uuid)
            )
