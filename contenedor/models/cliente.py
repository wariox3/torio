import re

from django.db import models, transaction
from tenant_users.permissions.models import UserTenantPermissions
from tenant_users.tenants.models import (
    DeleteError,
    ExistsError,
    TenantBase,
    schema_required,
    tenant_user_added,
    tenant_user_removed,
)


class CtnCliente(TenantBase):
    # Ciclo de vida del contenedor. `CtnClienteViewSet.create` lo registra en
    # `creando` y la tarea `crear_contenedor` lo lleva a `listo` o a `error`; mientras
    # no esté `listo`, `TenantHeaderMiddleware` no deja entrar a su schema.
    #
    # El default es `listo` y no `creando` porque todo lo que crea un contenedor con
    # `save()` —`TenantTestCase`, el shell, el admin— lo deja completo en ese mismo
    # llamado (`auto_create_schema`). Solo la vista lo difiere, y lo marca ella.
    #
    # No es `activo`: ese dice si el contenedor está habilitado, este si ya terminó
    # de construirse. Un contenedor listo puede estar inactivo, y al revés.
    ESTADO_CREANDO = 'creando'
    ESTADO_LISTO = 'listo'
    ESTADO_ERROR = 'error'
    ESTADO_CHOICES = [
        (ESTADO_CREANDO, 'Creando'),
        (ESTADO_LISTO, 'Listo'),
        (ESTADO_ERROR, 'Error'),
    ]

    # Qué nombre de schema se acepta al crear un contenedor. No sirve el
    # `is_valid_schema_name` de django-tenants: es `^(?!pg_).{1,63}$`, que deja pasar
    # comillas, y el nombre va interpolado en `CREATE SCHEMA "<nombre>"`.
    SCHEMA_NAME_VALIDO = re.compile(r'^(?!pg_)[a-z][a-z0-9_]{0,62}$')

    schema_name = models.CharField(max_length=100, unique=True)
    nombre = models.CharField('Nombre', max_length=100)
    celular = models.CharField('Celular', max_length=20)
    correo = models.EmailField('Correo', max_length=255)
    activo = models.BooleanField('Activo', default=True, db_default=True)
    estado = models.CharField(
        'Estado', max_length=10, choices=ESTADO_CHOICES,
        default=ESTADO_LISTO, db_default=ESTADO_LISTO,
    )
    # Imagen del contenedor en la interfaz (no el logotipo de los formatos, que es
    # `GenConfiguracion.gen_empresa_logotipo`). Un uuid por juego de derivados: las
    # keys las arma `contenedor.imagen`. Null = sin imagen.
    imagen_uuid = models.UUIDField(null=True)
    fecha_creacion = models.DateTimeField(null=True, auto_now_add=True)
    # La marca `POST /contenedor/cliente/<id>/ingresar/`. Arranca en la de creación.
    fecha_ultima_conexion = models.DateTimeField(null=True, auto_now_add=True)
    owner = models.ForeignKey(
        'seguridad.SegUsuario',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    suscripcion = models.ForeignKey(
        'contenedor.CtnSuscripcion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    auto_create_schema = True
    auto_drop_schema = True

    class Meta:
        db_table = "ctn_cliente"
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
                

    def __str__(self):
        return self.nombre

    @schema_required
    @transaction.atomic
    def add_user(
        self, user_obj, *, grupos=None, propietario=False, soporte=False,
        is_superuser=False, is_staff=False,
    ):
        """
        Vincula un usuario al contenedor.

        Sobreescribe el `add_user` de `TenantBase` porque en este proyecto la
        autorización vive en la membresía (público), no en `UserTenantPermissions`:
        `SegUsuarioCliente` lleva `propietario`, `soporte` e `is_superuser`, y
        `SegUsuarioClienteGrupo` sus grupos. Es lo que lee `SegUsuario.has_perm()`
        dentro del contenedor, sin entrar a su schema.

        `UserTenantPermissions` se sigue creando, vacío (sin grupos ni
        superusuario), solo por compatibilidad con django-tenant-users: no decide
        nada. `@schema_required` conmuta al schema del tenant para escribirlo.

        `propietario` marca al dueño del contenedor, pero no autoriza nada: quien
        autoriza es `grupos`, y el salto de `TienePermisoModelo` lo da
        `is_superuser`. Un usuario sin grupos entra al contenedor pero no pasa
        `TienePermisoModelo` en ningún recurso protegido.

        Hay una única excepción a escribir todo junto: el owner de un contenedor
        nuevo. `CtnClienteViewSet.create` crea su membresía (con `is_superuser`)
        en el request, cuando el schema todavía no tiene tablas, y
        `crear_contenedor` crea su `UserTenantPermissions` al terminar las
        migraciones. Entre una cosa y la otra el contenedor está en `creando`, y
        el middleware no deja entrar a nadie.
        """
        from seguridad.models import SegUsuarioCliente, SegUsuarioClienteGrupo

        if SegUsuarioCliente.objects.filter(usuario=user_obj, cliente=self).exists():
            raise ExistsError(f'El usuario ya es miembro de {self.nombre}.')

        UserTenantPermissions.objects.create(profile=user_obj, is_staff=is_staff)

        membresia = SegUsuarioCliente.objects.create(
            usuario=user_obj,
            cliente=self,
            propietario=propietario,
            soporte=soporte,
            is_superuser=is_superuser,
        )
        SegUsuarioClienteGrupo.objects.bulk_create([
            SegUsuarioClienteGrupo(usuario_cliente=membresia, grupo=grupo)
            for grupo in set(grupos or [])
        ])

        tenant_user_added.send(sender=self.__class__, user=user_obj, tenant=self)
        return membresia

    @schema_required
    @transaction.atomic
    def remove_user(self, user_obj):
        """
        Desvincula un usuario del contenedor: borra su `UserTenantPermissions`
        del schema del tenant y su fila de `SegUsuarioCliente` (con sus grupos,
        por CASCADE).

        Sobreescribe el de `TenantBase` por la misma razón que `add_user`, y
        porque el original prohíbe sacar al owner apoyándose en `self.owner.pk`,
        que en este proyecto es nulable.

        Borrar la fila de permisos no es opcional: `UserTenantPermissions.profile`
        es OneToOne, así que una fila huérfana impide volver a invitar al mismo
        usuario a este contenedor.
        """
        from seguridad.models import SegUsuarioCliente

        if user_obj.pk == self.owner_id:
            raise DeleteError(f'No se puede desvincular al owner de {self.nombre}.')

        UserTenantPermissions.objects.filter(profile=user_obj).delete()
        SegUsuarioCliente.objects.filter(usuario=user_obj, cliente=self).delete()

        tenant_user_removed.send(sender=self.__class__, user=user_obj, tenant=self)

    def es_superusuario(self, usuario):
        """
        ¿El usuario tiene `is_superuser` DENTRO de este contenedor?

        La fuente de verdad es su membresía (`SegUsuarioCliente.is_superuser`) —la
        misma que consulta `has_perm()`— y no `owner_id`, que es un dato
        informativo y nulable. La creación del contenedor marca al owner.
        """
        if usuario is None or not usuario.is_authenticated:
            return False
        # El staff en soporte tiene `is_superuser` para trabajar dentro del
        # contenedor, pero modificarlo o eliminarlo es cosa del cliente.
        from seguridad.models import SegUsuarioCliente
        return SegUsuarioCliente.objects.filter(
            usuario=usuario, cliente=self, is_superuser=True, soporte=False,
        ).exists()