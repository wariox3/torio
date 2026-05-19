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
    nombre_corto = models.CharField(max_length=255, null=True)
    numero_identificacion = models.CharField(max_length=20, null=True)
    celular = models.CharField(max_length=50, null=True)
    idioma = models.CharField(max_length=2, default='es', db_default='es')
    imagen = models.TextField(default='usuarios/imagen_defecto.jpg', db_default='usuarios/imagen_defecto.jpg')
    imagen_thumbnail = models.TextField(default='usuarios/imagen_defecto.jpg', db_default='usuarios/imagen_defecto.jpg')
    saldo_pendiente = models.DecimalField(max_digits=14, decimal_places=2, default=0, db_default=0)
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

    def tiene_permiso(self, codigo, tenant):
        if self.is_superuser:
            return True
        return self.membresias.filter(
            cliente=tenant,
            rol__activo=True,
            rol__permisos__codigo=codigo,
        ).exists()

    def rol_en(self, tenant):
        membresia = self.membresias.filter(cliente=tenant).select_related('rol').first()
        return membresia.rol if membresia else None