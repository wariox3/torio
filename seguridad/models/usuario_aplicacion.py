from django.db import models


class SegUsuarioAplicacion(models.Model):
    """Relación entre un usuario y una aplicación (`CtnAplicacion`)."""

    usuario = models.ForeignKey(
        'seguridad.SegUsuario', on_delete=models.CASCADE, related_name='aplicaciones',
    )
    aplicacion = models.ForeignKey('contenedor.CtnAplicacion', on_delete=models.PROTECT)

    class Meta:
        db_table = 'seg_usuario_aplicacion'
        verbose_name = 'Usuario-Aplicación'
        verbose_name_plural = 'Usuario-Aplicaciones'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'aplicacion'], name='seg_usuario_aplicacion_unico',
            ),
        ]

    def __str__(self):
        return f'{self.usuario_id} - {self.aplicacion_id}'
