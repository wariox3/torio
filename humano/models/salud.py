from django.db import models


class HumSalud(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    porcentaje_empleado = models.DecimalField(max_digits=6, decimal_places=3, default=4, db_default=4)
    concepto = models.ForeignKey(
        'humano.HumConcepto', null=True, on_delete=models.PROTECT,
        related_name='saludes_concepto_rel',
    )

    class Meta:
        db_table = 'hum_salud'
        ordering = ['nombre']
        verbose_name = 'Salud'
        verbose_name_plural = 'Saludes'

    def __str__(self):
        return self.nombre
