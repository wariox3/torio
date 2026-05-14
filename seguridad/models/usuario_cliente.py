from django.db import models


class SegUsuarioCliente(models.Model):
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        db_column='usuario_id',
        related_name='membresias',
    )
    cliente = models.ForeignKey(
        'contenedor.CtnCliente',
        on_delete=models.CASCADE,
        db_column='cliente_id',
    )
    rol = models.ForeignKey(
        'seguridad.SegRol',
        null=True,
        on_delete=models.SET_NULL,
        related_name='membresias',
    )

    class Meta:
        db_table = 'seg_usuario_cliente'
        verbose_name = 'Usuario-Cliente'
        verbose_name_plural = 'Usuario-Clientes'
        unique_together = [['usuario', 'cliente']]
