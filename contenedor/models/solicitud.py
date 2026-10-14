from django.db import models
from django.db.models import Q


class CtnSolicitud(models.Model):
    """
    Lo que un contenedor le pide a torio (un certificado de firma, por ahora). Es
    genérica: el tipo dice qué se pide, y los documentos van como `CtnArchivo` con
    `modelo` = 1 (`CtnModelo`) y `objeto_id` = el id de la solicitud.

    Nace `pendiente`. `rechazada` y `atendida` existen para la gestión del staff,
    que todavía no está: hoy nada las asigna.
    """

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_RECHAZADA = 'rechazada'
    ESTADO_ATENDIDA = 'atendida'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_RECHAZADA, 'Rechazada'),
        (ESTADO_ATENDIDA, 'Atendida'),
    ]

    estado = models.CharField(
        max_length=10, choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE, db_default=ESTADO_PENDIENTE,
    )
    # El del cliente al pedir y el del staff al gestionar (p. ej. por qué se rechazó).
    comentario = models.CharField(max_length=500, null=True)
    observacion = models.CharField(max_length=500, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_atencion = models.DateTimeField(null=True)
    cliente = models.ForeignKey(
        'contenedor.CtnCliente', on_delete=models.CASCADE, related_name='solicitudes',
    )
    solicitud_tipo = models.ForeignKey('contenedor.CtnSolicitudTipo', on_delete=models.PROTECT)
    # Quien la pidió y el staff que la gestione. SET_NULL: la solicitud es historia
    # del contenedor y sobrevive a que se borre la cuenta.
    usuario = models.ForeignKey(
        'seguridad.SegUsuario', null=True, on_delete=models.SET_NULL, related_name='+',
    )
    usuario_gestion = models.ForeignKey(
        'seguridad.SegUsuario', null=True, on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        db_table = 'ctn_solicitud'
        ordering = ['-id']
        verbose_name = 'Solicitud'
        verbose_name_plural = 'Solicitudes'
        constraints = [
            # Una pendiente por contenedor y tipo: dos pedidos del mismo certificado
            # a la vez serían trabajo doble para el staff.
            models.UniqueConstraint(
                fields=['cliente', 'solicitud_tipo'],
                condition=Q(estado='pendiente'),
                name='ctn_solicitud_una_pendiente',
            ),
        ]

    def __str__(self):
        return f'{self.solicitud_tipo_id} - {self.cliente_id}'
