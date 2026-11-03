from django.conf import settings
from django.contrib.auth.models import Permission
from django.db import connection, models
from django_tenants.utils import get_public_schema_name
from tenant_users.permissions.functional import tenant_cached_property
from tenant_users.permissions.models import UserTenantPermissions
from tenant_users.tenants.models import UserProfile


def _en_contenedor():
    """¿La conexión está en el schema de un contenedor (no en el público)?"""
    return (
        getattr(connection, 'tenant', None) is not None
        and connection.schema_name != get_public_schema_name()
    )


class SegUsuario(UserProfile):
    # Heredados de UserProfile
    # email = models.EmailField(unique=True, db_index=True)   <- USERNAME_FIELD
    # is_active = models.BooleanField(default=True)
    # is_verified = models.BooleanField(default=False)
    # Heredados de AbstractBaseUser
    # password = ...
    # last_login = models.DateTimeField(null=True)
    nombre_corto = models.CharField(max_length=255, null=True)
    numero_identificacion = models.CharField(max_length=20, null=True)
    celular = models.CharField(max_length=50, null=True)
    idioma = models.CharField(max_length=2, default='es', db_default='es')
    # Un solo uuid por juego de derivados: las dos keys se arman con
    # `seguridad.foto.key_original`/`key_thumbnail`. Guardar las dos rutas por
    # separado permitía que quedaran desincronizadas entre sí. Null = sin foto,
    # y el front decide qué mostrar en su lugar.
    imagen_uuid = models.UUIDField(null=True)
    fecha_nacimiento = models.DateField(null=True)
    fecha_creacion = models.DateTimeField(null=True, auto_now_add=True)
    tenants = models.ManyToManyField(
        settings.TENANT_MODEL,
        through='seguridad.SegUsuarioCliente',
        related_name='user_set',
        blank=True,
    )
    class Meta:
        db_table = "seg_usuario"
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email

    # --- Autorización -------------------------------------------------------
    #
    # Dentro de un contenedor, los permisos salen de la membresía en el público
    # (`SegUsuarioCliente.is_superuser`, `SegUsuarioClienteGrupo` y
    # `SegUsuarioClientePermiso`), no de
    # `UserTenantPermissions` como hace django-tenant-users: así se pueden leer
    # sin entrar al schema del contenedor. En el público se deja la librería tal
    # cual, porque ahí `is_staff`/`is_superuser` son los de la plataforma
    # (`EsStaff`, `createsuperuser`).
    #
    # `tenant_cached_property` guarda el resultado por schema en la instancia,
    # que vive lo que la petición: una consulta por petición y contenedor.

    @tenant_cached_property
    def _permisos_contenedor(self):
        """(is_superuser, {'app_label.codename'}) en el contenedor activo."""
        from seguridad.models import SegUsuarioCliente

        membresia = SegUsuarioCliente.objects.filter(
            usuario_id=self.pk, cliente_id=connection.tenant.pk,
        ).values_list('id', 'is_superuser').first()
        if membresia is None:
            return False, frozenset()
        membresia_id, es_superusuario = membresia
        if es_superusuario:
            return True, frozenset()
        # Se suman: los de sus grupos con `heredar_permisos` y sus permisos
        # personalizados. Un grupo sin `heredar_permisos` no aporta nada acá.
        campos = ('content_type__app_label', 'codename')
        de_grupos = Permission.objects.filter(
            group__segusuarioclientegrupo__usuario_cliente_id=membresia_id,
            group__segusuarioclientegrupo__heredar_permisos=True,
        ).values_list(*campos).order_by()
        personalizados = Permission.objects.filter(
            segusuarioclientepermiso__usuario_cliente_id=membresia_id,
        ).values_list(*campos).order_by()
        permisos = de_grupos.union(personalizados)
        return False, frozenset(f'{app_label}.{codename}' for app_label, codename in permisos)

    def _permisos_en_contenedor(self):
        es_superusuario, permisos = self._permisos_contenedor
        if not es_superusuario:
            return set(permisos)
        return {
            f'{app_label}.{codename}'
            for app_label, codename in Permission.objects.values_list(
                'content_type__app_label', 'codename',
            )
        }

    @tenant_cached_property
    def is_superuser(self) -> bool:
        if _en_contenedor():
            return self._permisos_contenedor[0]
        try:
            return self.tenant_perms.is_superuser
        except UserTenantPermissions.DoesNotExist:
            return False

    def get_group_permissions(self, obj=None) -> set[str]:
        if _en_contenedor():
            return self._permisos_en_contenedor() if obj is None else set()
        return super().get_group_permissions(obj)

    def get_all_permissions(self, obj=None) -> set[str]:
        if _en_contenedor():
            return self._permisos_en_contenedor() if obj is None else set()
        return super().get_all_permissions(obj)

    def has_perm(self, perm: str, obj=None) -> bool:
        if _en_contenedor():
            if not self.is_active:
                return False
            es_superusuario, permisos = self._permisos_contenedor
            return es_superusuario or (obj is None and perm in permisos)
        return super().has_perm(perm, obj)

    def has_perms(self, perm_list, obj=None) -> bool:
        if _en_contenedor():
            return all(self.has_perm(perm, obj) for perm in perm_list)
        return super().has_perms(perm_list, obj)

    def has_module_perms(self, app_label: str) -> bool:
        if _en_contenedor():
            if not self.is_active:
                return False
            es_superusuario, permisos = self._permisos_contenedor
            return es_superusuario or any(p.startswith(f'{app_label}.') for p in permisos)
        return super().has_module_perms(app_label)