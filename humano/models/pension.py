from django.db import models


class HumPension(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    porcentaje_empleado = models.DecimalField(max_digits=6, decimal_places=3, default=0, db_default=0)
    porcentaje_empleador = models.DecimalField(max_digits=6, decimal_places=3, default=0, db_default=0)
    concepto = models.ForeignKey(
        'humano.HumConcepto', null=True, on_delete=models.PROTECT,
        related_name='pensiones_concepto_rel',
    )

    class Meta:
        db_table = 'hum_pension'
        ordering = ['nombre']
        verbose_name = 'Pensión'
        verbose_name_plural = 'Pensiones'

    def __str__(self):
        return self.nombre
