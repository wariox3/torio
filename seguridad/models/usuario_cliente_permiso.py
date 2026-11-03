from django.db import models


class SegUsuarioClientePermiso(models.Model):
    """
    Permisos personalizados de un miembro en un contenedor: cualquier
    `auth.Permission`, pertenezca o no a sus grupos. Se suman a los de sus grupos
    con `heredar_permisos` (`SegUsuario.has_perm()`); nunca restan. Cuelga de la
    membresía: al salir del contenedor se borran con ella.
    """

    usuario_cliente = models.ForeignKey(
        'seguridad.SegUsuarioCliente', on_delete=models.CASCADE, related_name='permisos',
    )
    permiso = models.ForeignKey('auth.Permission', on_delete=models.CASCADE)

    class Meta:
        db_table = 'seg_usuario_cliente_permiso'
        verbose_name = 'Usuario-Cliente-Permiso'
        verbose_name_plural = 'Usuario-Cliente-Permisos'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario_cliente', 'permiso'], name='seg_usuario_cliente_permiso_unico',
            ),
        ]

    def __str__(self):
        return f'{self.usuario_cliente_id} - {self.permiso_id}'
