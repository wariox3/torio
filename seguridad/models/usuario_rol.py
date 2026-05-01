from django.db import models


class SegUsuarioRol(models.Model):
    usuario = models.ForeignKey(
        'seguridad.SegUsuario', on_delete=models.CASCADE, related_name='asignaciones_rol',
    )
    rol = models.ForeignKey(
        'seguridad.SegRol', on_delete=models.PROTECT, related_name='asignaciones',
    )
    tenant = models.ForeignKey(
        'contenedor.CtnCliente', on_delete=models.CASCADE, related_name='asignaciones_rol',
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seg_usuario_rol'
        verbose_name = 'Rol de Usuario'
        verbose_name_plural = 'Roles de Usuarios'
        unique_together = [['usuario', 'rol', 'tenant']]
        indexes = [
            models.Index(fields=['usuario', 'tenant']),
        ]

    def __str__(self):
        return f'{self.usuario} → {self.rol} @ {self.tenant}'
