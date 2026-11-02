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
    # Grupos de permisos que se le otorgarán al usuario al aceptar. Es lo que se
    # copia a su UserTenantPermissions dentro del schema del contenedor.
    # El `through` explícito es solo para nombrar las columnas de la tabla
    # intermedia: la automática las llamaría `ctninvitacion_id` y `group_id`.
    grupos = models.ManyToManyField(
        'auth.Group',
        blank=True,
        related_name='invitaciones',
        through='contenedor.CtnInvitacionGrupo',
    )
    # Aplicaciones que verá el invitado en este contenedor. Se eligen al invitar y
    # al aceptar se copian a su membresía (`SegUsuarioClienteAplicacion`).
    aplicaciones = models.ManyToManyField(
        'contenedor.CtnAplicacion',
        blank=True,
        related_name='invitaciones',
        through='contenedor.CtnInvitacionAplicacion',
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


class CtnInvitacionGrupo(models.Model):
    """Tabla intermedia de `CtnInvitacion.grupos`, solo para fijar los nombres
    de columna. No lleva datos propios."""

    invitacion = models.ForeignKey(
        'contenedor.CtnInvitacion',
        on_delete=models.CASCADE,
        db_column='invitacion_id',
    )
    grupo = models.ForeignKey(
        'auth.Group',
        on_delete=models.CASCADE,
        db_column='grupo_id',
    )

    class Meta:
        db_table = 'ctn_invitacion_grupo'
        unique_together = [['invitacion', 'grupo']]


class CtnInvitacionAplicacion(models.Model):
    """Tabla intermedia de `CtnInvitacion.aplicaciones`."""

    invitacion = models.ForeignKey('contenedor.CtnInvitacion', on_delete=models.CASCADE)
    aplicacion = models.ForeignKey('contenedor.CtnAplicacion', on_delete=models.PROTECT)

    class Meta:
        db_table = 'ctn_invitacion_aplicacion'
        constraints = [
            models.UniqueConstraint(
                fields=['invitacion', 'aplicacion'], name='ctn_invitacion_aplicacion_unico',
            ),
        ]
