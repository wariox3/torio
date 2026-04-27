from django.db import models
from tenant_users.tenants.models import UserProfile


class SegUsuario(UserProfile):
    # Heredados de UserProfile
    # email = models.EmailField(unique=True, db_index=True)   <- USERNAME_FIELD
    # is_active = models.BooleanField(default=True)
    # is_verified = models.BooleanField(default=False)
    # tenants = models.ManyToManyField(TENANT_MODEL, ...)
    # Heredados de AbstractBaseUser
    # password = ...
    # last_login = models.DateTimeField(null=True)    
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