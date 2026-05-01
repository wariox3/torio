from django.conf import settings
from django.db import models
from tenant_users.tenants.models import UserProfile


class SegUsuario(UserProfile):
    # Heredados de UserProfile
    # email = models.EmailField(unique=True, db_index=True)   <- USERNAME_FIELD
    # is_active = models.BooleanField(default=True)
    # is_verified = models.BooleanField(default=False)
    # Heredados de AbstractBaseUser
    # password = ...
    # last_login = models.DateTimeField(null=True)
    tenants = models.ManyToManyField(
        settings.TENANT_MODEL,
        through='seguridad.SegUsuarioTenant',
        related_name='user_set',
        blank=True,
    )
    nombre_corto = models.CharField(max_length=255, null=True)
    numero_identificacion = models.CharField(max_length=20, null=True)
    celular = models.CharField(max_length=50, null=True)
    idioma = models.CharField(max_length=2, default='es')
    imagen = models.TextField(null=True)
    imagen_thumbnail = models.TextField(null=True)        
    fecha_creacion = models.DateTimeField(null=True, auto_now_add=True)

    class Meta:
        db_table = "seg_usuario"
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email

    def tiene_permiso(self, codigo, tenant):
        if self.is_superuser:
            return True
        return self.asignaciones_rol.filter(
            tenant=tenant,
            rol__activo=True,
            rol__permisos__codigo=codigo,
        ).exists()

    def roles_en(self, tenant):
        from seguridad.models import SegRol
        return SegRol.objects.filter(
            asignaciones__usuario=self,
            asignaciones__tenant=tenant,
            activo=True,
        ).distinct()