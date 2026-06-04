from django.db import models


class HumConceptoNomina(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    concepto = models.ForeignKey(
        'humano.HumConcepto', null=True, on_delete=models.PROTECT,
        related_name='conceptos_nomina_concepto_rel',
    )

    class Meta:
        db_table = 'hum_concepto_nomina'
        ordering = ['nombre']
        verbose_name = 'Concepto nómina'
        verbose_name_plural = 'Conceptos nómina'

    def __str__(self):
        return self.nombre
