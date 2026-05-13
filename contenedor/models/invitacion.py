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
    invitado_por = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.PROTECT,
        related_name='invitaciones_enviadas',
    )
    correo = models.EmailField()
    estado = models.CharField(max_length=1, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    fecha_envio = models.DateTimeField(auto_now_add=True)
    fecha_expira = models.DateTimeField()
    token = models.CharField(max_length=500, unique=True)

    class Meta:
        db_table = 'ctn_invitacion'
        verbose_name = 'Invitación'
        verbose_name_plural = 'Invitaciones'
        unique_together = [['cliente', 'correo']]

    def __str__(self):
        return f'{self.correo} → {self.cliente} ({self.get_estado_display()})'
