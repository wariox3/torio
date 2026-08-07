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
    schema_name = models.CharField(max_length=100, unique=True)
    nombre = models.CharField('Nombre', max_length=100)
    telefono = models.CharField('Teléfono', max_length=20)
    correo = models.EmailField('Correo', max_length=255)
    activo = models.BooleanField('Activo', default=True, db_default=True)
    fecha_creacion = models.DateTimeField(null=True, auto_now_add=True)
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
    def add_user(self, user_obj, *, grupos=None, accesos=None, propietario=False, is_superuser=False, is_staff=False):
        """
        Vincula un usuario al contenedor.

        Sobreescribe el `add_user` de `TenantBase` porque la membresía de este
        proyecto lleva datos que la librería no conoce (`propietario` y los flags
        `acceso_*` de `SegUsuarioCliente`). Hace lo mismo que el original y en el
        mismo orden: la fila de permisos en el schema del tenant y la de
        membresía en el público, ambas dentro de la misma transacción.

        Las dos escrituras van juntas a propósito. `SegUsuarioCliente` dice de
        qué contenedores es miembro el usuario; `UserTenantPermissions` es lo
        único que `has_perm()` lee dentro de un tenant. Si falta la segunda, el
        usuario entra al contenedor sin ningún permiso.

        `propietario` marca al dueño del contenedor, pero no autoriza nada: quien
        autoriza es `grupos`, y el salto de `TienePermisoModelo` lo da
        `is_superuser`. Un usuario sin grupos entra al contenedor pero no pasa
        `TienePermisoModelo` en ningún recurso protegido.

        `accesos` es un dict {campo de `CAMPOS_ACCESO`: bool} con los módulos que
        el usuario verá en el menú. Omitirlo deja todos en False (el default del
        modelo): ser miembro no concede acceso a ningún módulo por sí solo.

        `@schema_required` conmuta al schema del tenant: `UserTenantPermissions`
        y sus grupos caen ahí, y `seg_usuario_cliente` y `auth_group` se
        resuelven a `public` por el search_path.
        """
        from seguridad.models import CAMPOS_ACCESO, SegUsuarioCliente

        if SegUsuarioCliente.objects.filter(usuario=user_obj, cliente=self).exists():
            raise ExistsError(f'El usuario ya es miembro de {self.nombre}.')

        permisos = UserTenantPermissions.objects.create(
            profile=user_obj,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        if grupos:
            permisos.groups.set(grupos)

        membresia = SegUsuarioCliente.objects.create(
            usuario=user_obj,
            cliente=self,
            propietario=propietario,
            **{campo: bool((accesos or {}).get(campo, False)) for campo in CAMPOS_ACCESO},
        )

        tenant_user_added.send(sender=self.__class__, user=user_obj, tenant=self)
        return membresia

    @schema_required
    @transaction.atomic
    def remove_user(self, user_obj):
        """
        Desvincula un usuario del contenedor: borra su `UserTenantPermissions`
        del schema del tenant y su fila de `SegUsuarioCliente`.

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

    @schema_required
    def es_superusuario(self, usuario):
        """
        ¿El usuario tiene `is_superuser` DENTRO de este contenedor?

        La fuente de verdad es `permissions_usertenantpermissions` del schema del
        tenant — la misma que consulta `has_perm()` — y no `owner_id`, que es un
        dato informativo y nulable. `add_user` marca `is_superuser=True` al owner
        cuando se crea el contenedor.

        Nota: el contenedor del schema público queda protegido por construcción,
        porque su tabla de permisos solo tiene filas si se crea un superusuario
        de plataforma con `createsuperuser`.
        """
        if usuario is None or not usuario.is_authenticated:
            return False
        return UserTenantPermissions.objects.filter(
            profile_id=usuario.pk,
            is_superuser=True,
        ).exists()