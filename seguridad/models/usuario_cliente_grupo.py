from django.db import models


class SegUsuarioClienteGrupo(models.Model):
    """
    Grupos de permisos (`auth.Group`) de un miembro en un contenedor. Es la fuente
    de verdad de la autorización dentro del tenant: `SegUsuario.has_perm()` lee de
    acá, en el público, y no de `UserTenantPermissions`. Cuelga de la membresía:
    al salir del contenedor se borran con ella.
    """

    usuario_cliente = models.ForeignKey(
        'seguridad.SegUsuarioCliente', on_delete=models.CASCADE, related_name='grupos',
    )
    grupo = models.ForeignKey('auth.Group', on_delete=models.CASCADE)

    class Meta:
        db_table = 'seg_usuario_cliente_grupo'
        verbose_name = 'Usuario-Cliente-Grupo'
        verbose_name_plural = 'Usuario-Cliente-Grupos'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario_cliente', 'grupo'], name='seg_usuario_cliente_grupo_unico',
            ),
        ]

    def __str__(self):
        return f'{self.usuario_cliente_id} - {self.grupo_id}'
