from django.db import models


class SegUsuarioClienteAplicacion(models.Model):
    """
    Aplicaciones (módulos) que un miembro ve en un contenedor. Cuelga de la
    membresía: al salir del contenedor se borran con ella. No autoriza nada —eso
    lo hacen los grupos—, solo arma el menú y filtra los pendientes. Las elige el
    dueño al invitar y las edita después.
    """

    usuario_cliente = models.ForeignKey(
        'seguridad.SegUsuarioCliente', on_delete=models.CASCADE, related_name='aplicaciones',
    )
    aplicacion = models.ForeignKey('contenedor.CtnAplicacion', on_delete=models.PROTECT)

    class Meta:
        db_table = 'seg_usuario_cliente_aplicacion'
        verbose_name = 'Usuario-Cliente-Aplicación'
        verbose_name_plural = 'Usuario-Cliente-Aplicaciones'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario_cliente', 'aplicacion'],
                name='seg_usuario_cliente_aplicacion_unico',
            ),
        ]

    def __str__(self):
        return f'{self.usuario_cliente_id} - {self.aplicacion_id}'
