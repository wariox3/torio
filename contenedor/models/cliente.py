from django.db import models
from tenant_users.tenants.models import TenantBase


class CtnCliente(TenantBase):
    schema_name = models.CharField(max_length=100)
    nombre = models.CharField('Nombre', max_length=100)
    activo = models.BooleanField('Activo', default=True)
    fecha_creacion = models.DateTimeField(null=True, auto_now_add=True)
    fecha_ultima_conexion = models.DateTimeField(null=True, auto_now_add=True)
    owner = models.ForeignKey(
        'seguridad.SegUsuario',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    auto_create_schema = True

    class Meta:
        db_table = "ctn_cliente"
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
                

    def __str__(self):
        return self.nombre