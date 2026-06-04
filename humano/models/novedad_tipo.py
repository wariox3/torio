from django.db import models


class HumNovedadTipo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    novedad_clase_id = models.IntegerField(null=True)
    concepto = models.ForeignKey(
        'humano.HumConcepto', null=True, on_delete=models.PROTECT,
        related_name='novedades_tipos_concepto_rel',
    )
    concepto2 = models.ForeignKey(
        'humano.HumConcepto', null=True, on_delete=models.PROTECT,
        related_name='novedades_tipos_concepto2_rel',
    )

    class Meta:
        db_table = 'hum_novedad_tipo'
        ordering = ['nombre']
        verbose_name = 'Novedad tipo'
        verbose_name_plural = 'Novedades tipos'

    def __str__(self):
        return self.nombre
