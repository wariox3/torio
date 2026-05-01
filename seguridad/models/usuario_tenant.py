from django.db import models


class SegUsuarioTenant(models.Model):
    usuario = models.ForeignKey(
        'seguridad.SegUsuario', on_delete=models.CASCADE, db_column='usuario_id',
    )
    cliente = models.ForeignKey(
        'contenedor.CtnCliente', on_delete=models.CASCADE, db_column='cliente_id',
    )

    class Meta:
        db_table = 'seg_usuario_tenants'
        verbose_name = 'Usuario-Tenant'
        verbose_name_plural = 'Usuario-Tenants'
        unique_together = [['usuario', 'cliente']]
