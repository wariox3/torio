from django.db import models


class VenTurno(models.Model):
    """
    Un turno de una caja: lo abre un cajero con una base de efectivo, recibe las
    facturas POS que él hace y al cerrarse compara lo esperado con lo contado por
    cada cuenta bancaria (`VenTurnoDetalle`).

    Las facturas se amarran al turno con `GenDocumento.turno` y no por fecha,
    porque `GenDocumentoPago` no tiene fecha. Ver `venta/servicios/turno.py`.

    `total_venta` y `cantidad_documentos` se escriben al cerrar y no se
    recalculan: si después se anula una factura, el cierre queda como lo vio el
    cajero.
    """

    fecha_apertura = models.DateTimeField()
    fecha_cierre = models.DateTimeField(null=True)
    base = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total_venta = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cantidad_documentos = models.IntegerField(default=0, db_default=0)
    estado_cerrado = models.BooleanField(default=False, db_default=False)
    comentario = models.CharField(max_length=500, null=True)
    caja = models.ForeignKey(
        'venta.VenCaja',
        on_delete=models.PROTECT,
        related_name='turnos_caja_rel',
    )
    # El cajero: el único que factura en el turno.
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.PROTECT,
        related_name='turnos_usuario_rel',
    )
    # La cuenta donde está la base, normalmente la de efectivo de la caja. En el
    # arqueo la base se suma a lo esperado de esta cuenta.
    cuenta_banco = models.ForeignKey(
        'general.GenCuentaBanco',
        null=True,
        on_delete=models.PROTECT,
        related_name='turnos_cuenta_banco_rel',
    )

    class Meta:
        db_table = 'ven_turno'
        ordering = ['-id']
        verbose_name = 'Turno'
        verbose_name_plural = 'Turnos'
        constraints = [
            # Un solo turno abierto por caja, también entre dos peticiones a la vez.
            models.UniqueConstraint(
                fields=['caja'],
                condition=models.Q(estado_cerrado=False),
                name='ven_turno_un_abierto_por_caja',
            ),
        ]

    def __str__(self):
        return f'{self.caja_id} - {self.fecha_apertura:%Y-%m-%d %H:%M}'
