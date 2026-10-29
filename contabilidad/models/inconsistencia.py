from django.db import models


class ConInconsistencia(models.Model):
    """Inconsistencia encontrada en el último análisis guardado de un periodo.

    Es una foto, no la verdad del momento: se reemplaza entera cada vez que el
    periodo se analiza (`periodo/analizar` o `periodo/bloquear`) y deja de
    estar al día apenas alguien corrige un movimiento. Para el estado actual
    están las consultas en vivo (`periodo/<id>/inconsistencias`).

    Todas las FKs son CASCADE: la fila es derivada, y borrar el documento o el
    asiento que la causa no puede quedar bloqueado por un registro viejo.
    """

    numero = models.BigIntegerField(null=True)
    descripcion = models.CharField(max_length=500)
    fecha = models.DateTimeField(auto_now_add=True)
    inconsistencia_tipo = models.ForeignKey(
        'contabilidad.ConInconsistenciaTipo', on_delete=models.PROTECT,
        related_name='inconsistencias_inconsistencia_tipo_rel',
    )
    periodo = models.ForeignKey(
        'contabilidad.ConPeriodo', on_delete=models.CASCADE,
        related_name='inconsistencias_periodo_rel',
    )
    comprobante = models.ForeignKey(
        'contabilidad.ConComprobante', null=True, on_delete=models.CASCADE,
        related_name='inconsistencias_comprobante_rel',
    )
    # La línea exacta que hay que corregir, en las reglas por movimiento. Nulo en el
    # descuadre (es del asiento entero) y en el documento sin contabilizar (aún no
    # tiene movimientos). La cuenta se lee de acá.
    movimiento = models.ForeignKey(
        'contabilidad.ConMovimiento', null=True, on_delete=models.CASCADE,
        related_name='inconsistencias_movimiento_rel',
    )
    documento = models.ForeignKey(
        'general.GenDocumento', null=True, on_delete=models.CASCADE,
        related_name='inconsistencias_documento_rel',
    )

    class Meta:
        db_table = 'con_inconsistencia'
        ordering = ['id']
        verbose_name = 'Inconsistencia'
        verbose_name_plural = 'Inconsistencias'

    def __str__(self):
        return self.descripcion
