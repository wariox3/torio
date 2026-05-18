from django.db import models


class CtnInvitacion(models.Model):
    ESTADO_PENDIENTE = 'P'
    ESTADO_ACEPTADA  = 'A'
    ESTADO_RECHAZADA = 'R'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_ACEPTADA,  'Aceptada'),
        (ESTADO_RECHAZADA, 'Rechazada'),
    ]

    cliente = models.ForeignKey(
        'contenedor.CtnCliente',
        on_delete=models.CASCADE,
        related_name='invitaciones',
    )
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        related_name='invitaciones_enviadas',
    )
    usuario_invitado = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        related_name='invitaciones_recibidas',
    )
    rol = models.ForeignKey(
        'seguridad.SegRol',
        null=True,
        on_delete=models.SET_NULL,
        related_name='invitaciones',
    )
    estado = models.CharField(max_length=1, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE, db_default=ESTADO_PENDIENTE)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ctn_invitacion'
        verbose_name = 'Invitación'
        verbose_name_plural = 'Invitaciones'
        unique_together = [['cliente', 'usuario_invitado']]

    def __str__(self):
        return f'{self.usuario_invitado} → {self.cliente} ({self.get_estado_display()})'
