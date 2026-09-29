"""
Tareas de Celery de `contenedor`.

Crear un contenedor cuesta unos 10 s de migraciones y otros tantos de catálogos, y
por eso no se hace en el request: `CtnClienteViewSet.create` registra el contenedor
en `creando` y encola `crear_contenedor`, que lo termina en el worker. El
diseño completo, y por qué, en `docs/creacion_contenedor.md`.
"""
import io
import logging
from contextlib import contextmanager

from celery import shared_task
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, transaction
from django_tenants.utils import get_public_schema_name, schema_context
from tenant_users.permissions.models import UserTenantPermissions

from contenedor.models import CtnCliente

logger = logging.getLogger(__name__)

# 30 s, 1 min y 2 min: lo que suele fallar acá es la base (una conexión cortada,
# un lock que no llegó), y eso se arregla solo en poco tiempo.
ESPERA_BASE_REINTENTO = 30
MAXIMO_REINTENTOS = 3

# Un contenedor tarda unos 20 s. El límite suave levanta `SoftTimeLimitExceeded`,
# que se reintenta como cualquier otra falla; el duro mata el proceso si ni eso
# alcanza a salir. Entre los dos queda margen para que la tarea marque el error.
LIMITE_SUAVE = 10 * 60
LIMITE_DURO = 11 * 60

# Cuánto vive en Redis el paso en curso. Es solo para mostrar el avance: si Redis
# no está, o la clave expiró, el front ve `estado` sin `paso` y nada más.
DURACION_PASO = 60 * 60

# Primera mitad de la clave del advisory lock de `_candado`; la segunda es el id del
# contenedor. Distingue estos locks de cualquier otro advisory lock de la base.
ESPACIO_CANDADO = 7301

PASO_ESQUEMA = 'esquema'
PASO_MIGRACIONES = 'migraciones'
PASO_PERMISOS = 'permisos'
PASO_CATALOGOS = 'catalogos'


def clave_paso(cliente_id):
    return f'contenedor:{cliente_id}:paso'


def programar_creacion(cliente_id):
    """
    Encola `crear_contenedor` cuando la transacción en curso se confirme.

    `on_commit` y no `delay` directo: el worker abre su propia conexión, y antes
    del COMMIT no vería ni el contenedor ni su schema.

    Si RabbitMQ no responde, el contenedor pasa a `error` en vez de quedarse en
    `creando` para siempre: así el front ofrece reintentar, que vuelve a encolar.
    """
    def encolar():
        try:
            crear_contenedor.delay(cliente_id)
        except Exception:
            logger.exception('No se pudo encolar la creación del contenedor %s', cliente_id)
            CtnCliente.objects.filter(
                pk=cliente_id, estado=CtnCliente.ESTADO_CREANDO,
            ).update(estado=CtnCliente.ESTADO_ERROR)

    transaction.on_commit(encolar)


@shared_task(
    bind=True,
    max_retries=MAXIMO_REINTENTOS,
    soft_time_limit=LIMITE_SUAVE,
    time_limit=LIMITE_DURO,
)
def crear_contenedor(self, cliente_id):
    """
    Termina de construir un contenedor registrado en `creando` y lo deja `listo`.

    Puede correr dos veces —`acks_late`, o un worker que muere a mitad— y en ese
    caso **retoma donde quedó** en vez de empezar de cero, porque cada paso se
    puede repetir sin daño:

    1. `CREATE SCHEMA IF NOT EXISTS`. Normalmente ya lo creó la vista.
    2. Las migraciones del tenant, **una transacción por migración**. Esto es lo
       que importa: las migraciones crean FKs hacia `seg_usuario`, `auth_group` y
       `auth_permission`, y cada FK deja esas tablas con `ShareRowExclusiveLock`
       hasta el COMMIT. En una sola transacción eran 10 s sin poder hacer
       `UPDATE` sobre `seg_usuario` —ni siquiera el `last_login` del login—; así
       son milisegundos por migración. Las ya aplicadas quedan en
       `django_migrations` del schema y no se repiten.
    3. `UserTenantPermissions` del owner, con `get_or_create`. Su membresía
       (`SegUsuarioCliente`) ya la creó la vista.
    4. Catálogos y semillas: `cargar_datos_tenant --inicial`, que ya es
       idempotente.
    5. `estado = listo`, recién acá: hasta este punto el middleware no deja entrar,
       así que nadie ve el contenedor vacío ni a medio sembrar.

    Si algo falla se reintenta; agotados los reintentos, el contenedor queda en
    `error` y el detalle en el log.

    El worker tiene dos procesos, así que dos ejecuciones para el mismo contenedor
    podrían correr a la vez; `_candado` deja pasar solo a una.
    """
    with _candado(cliente_id) as tomado:
        if not tomado:
            # Otra ejecución lo está construyendo: un reintento doble de uno
            # atascado, o una re-entrega de `acks_late` mientras la primera sigue
            # viva. Esa lo termina; dos a la vez migrarían el mismo schema.
            logger.info('El contenedor %s ya se está construyendo en otra ejecución', cliente_id)
            return

        cliente = CtnCliente.objects.filter(pk=cliente_id).first()
        # Borrado, ya terminado, o una entrega vieja de un contenedor que falló y
        # todavía no se reintentó: en ningún caso hay nada que hacer.
        if cliente is None or cliente.estado != CtnCliente.ESTADO_CREANDO:
            return

        schema_name = cliente.schema_name
        try:
            _construir(cliente)
        except Exception as error:
            if self.request.retries < self.max_retries:
                raise self.retry(
                    exc=error, countdown=ESPERA_BASE_REINTENTO * 2 ** self.request.retries,
                )
            logger.exception('Falló la creación del contenedor %s (%s)', cliente_id, schema_name)
            CtnCliente.objects.filter(
                pk=cliente_id, estado=CtnCliente.ESTADO_CREANDO,
            ).update(estado=CtnCliente.ESTADO_ERROR)
            return

        CtnCliente.objects.filter(
            pk=cliente_id, estado=CtnCliente.ESTADO_CREANDO,
        ).update(estado=CtnCliente.ESTADO_LISTO)
        logger.info('Contenedor %s (%s) listo', cliente_id, schema_name)


@contextmanager
def _candado(cliente_id):
    """
    Un advisory lock de PostgreSQL por contenedor: `True` si esta ejecución lo tomó.

    Va en una conexión propia y no en la de Django por dos razones:

    - `migrate_schemas` cierra la conexión de Django al terminar, y un lock de
      sesión se soltaría ahí, a mitad de la construcción.
    - Si el proceso muere, la conexión muere con él y PostgreSQL suelta el lock
      solo: la re-entrega de RabbitMQ lo encuentra libre.

    `try` y no un lock que espera: la segunda ejecución no tiene nada que hacer
    cuando la primera termine, así que sale enseguida.
    """
    conexion = connection.get_new_connection(connection.get_connection_params())
    try:
        conexion.autocommit = True
        with conexion.cursor() as cursor:
            cursor.execute(
                'SELECT pg_try_advisory_lock(%s, %s)', [ESPACIO_CANDADO, cliente_id],
            )
            tomado = cursor.fetchone()[0]
        yield tomado
    finally:
        # Cerrar la sesión suelta el lock.
        conexion.close()


def _construir(cliente):
    """Los pasos 1 a 4 de `crear_contenedor`, separados para poder probarlos."""
    schema_name = cliente.schema_name
    # El nombre ya lo validó la vista; se repite porque va interpolado en SQL.
    if not CtnCliente.SCHEMA_NAME_VALIDO.match(schema_name):
        raise ValueError(f'Nombre de schema inválido: {schema_name!r}')

    _anotar_paso(cliente.pk, PASO_ESQUEMA)
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

    _anotar_paso(cliente.pk, PASO_MIGRACIONES)
    # Fuera de cualquier `atomic`: así cada migración hace su propio COMMIT
    # (ver el paso 2 de `crear_contenedor`). `migrate_schemas` exige arrancar
    # desde el público y deja la conexión ahí al terminar.
    with schema_context(get_public_schema_name()):
        call_command(
            'migrate_schemas',
            tenant=True,
            schema_name=schema_name,
            interactive=False,
            verbosity=0,
            stdout=io.StringIO(),
        )

    _anotar_paso(cliente.pk, PASO_PERMISOS)
    # Sin owner no hay a quién dar permisos, y un contenedor sin nadie adentro
    # no sirve: mejor que termine en `error` y se vea.
    if cliente.owner_id is None:
        raise RuntimeError(f'El contenedor {cliente.pk} no tiene owner.')
    with schema_context(schema_name):
        UserTenantPermissions.objects.get_or_create(
            profile_id=cliente.owner_id,
            defaults={'is_superuser': True, 'is_staff': False},
        )

    _anotar_paso(cliente.pk, PASO_CATALOGOS)
    with schema_context(get_public_schema_name()):
        call_command(
            'cargar_datos_tenant',
            schema=schema_name,
            inicial=True,
            verbosity=0,
            stdout=io.StringIO(),
        )


def _anotar_paso(cliente_id, paso):
    """
    Deja en Redis el paso en curso, para `GET /contenedor/cliente/<id>/estado/`.

    Se anota desde el schema público a propósito: las claves de caché llevan el
    schema de la conexión (`django_tenants.cache.make_key`), y la vista las lee
    desde ahí. Con `IGNORE_EXCEPTIONS`, un Redis caído no interrumpe la creación.
    """
    with schema_context(get_public_schema_name()):
        cache.set(clave_paso(cliente_id), paso, timeout=DURACION_PASO)
