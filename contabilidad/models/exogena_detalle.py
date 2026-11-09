from django.db import models


class ConExogenaDetalle(models.Model):
    """Un formato que la empresa presenta en el año de su `ConExogena`.

    `cuantia_menor` es la del año: se copia de `ConExogenaFormato.cuantia_menor`
    al crear el detalle y se puede editar, porque la resolución la cambia de un
    año a otro y el catálogo solo trae la sugerida.

    `fecha_generacion`, `registros` y `total` resumen la última generación, para
    que el front muestre el avance sin recalcular.
    """

    cuantia_menor = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    fecha_generacion = models.DateTimeField(null=True)
    registros = models.IntegerField(default=0, db_default=0)
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    estado_generado = models.BooleanField(default=False, db_default=False)
    estado_presentado = models.BooleanField(default=False, db_default=False)
    exogena = models.ForeignKey(
        'contabilidad.ConExogena', on_delete=models.PROTECT,
        related_name='exogenas_detalles_exogena_rel',
    )
    formato = models.ForeignKey(
        'contabilidad.ConExogenaFormato', on_delete=models.PROTECT,
        related_name='exogenas_detalles_formato_rel',
    )

    class Meta:
        db_table = 'con_exogena_detalle'
        ordering = ['formato_id']
        verbose_name = 'Exógena detalle'
        verbose_name_plural = 'Exógenas detalles'
        constraints = [
            models.UniqueConstraint(fields=['exogena', 'formato'], name='con_exogena_detalle_exogena_formato_uniq'),
        ]

    def __str__(self):
        return f'{self.exogena_id} - {self.formato_id}'
