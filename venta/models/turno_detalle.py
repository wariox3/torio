from django.db import models


class VenTurnoDetalle(models.Model):
    """El arqueo de un turno cerrado: un renglón por cuenta bancaria."""

    esperado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    contado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    # contado - esperado: negativa si falta plata, positiva si sobra.
    diferencia = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    turno = models.ForeignKey(
        'venta.VenTurno',
        on_delete=models.PROTECT,
        related_name='turnos_detalles_turno_rel',
    )
    cuenta_banco = models.ForeignKey(
        'general.GenCuentaBanco',
        on_delete=models.PROTECT,
        related_name='turnos_detalles_cuenta_banco_rel',
    )

    class Meta:
        db_table = 'ven_turno_detalle'
        ordering = ['id']
        verbose_name = 'Turno detalle'
        verbose_name_plural = 'Turnos detalles'
        constraints = [
            models.UniqueConstraint(fields=['turno', 'cuenta_banco'], name='ven_turno_detalle_cuenta_unica'),
        ]

    def __str__(self):
        return f'{self.turno_id} - {self.cuenta_banco_id}'
