from django.db import models


class HumConcepto(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=80)
    porcentaje = models.DecimalField(max_digits=6, decimal_places=3, default=0, db_default=0)
    ingreso_base_prestacion = models.BooleanField(default=False, db_default=False)
    ingreso_base_prestacion_vacacion = models.BooleanField(default=False, db_default=False)
    ingreso_base_cotizacion = models.BooleanField(default=False, db_default=False)
    operacion = models.BigIntegerField(default=0, db_default=0)
    orden = models.IntegerField(default=0, db_default=0)
    adicional = models.BooleanField(default=False, db_default=False)
    concepto_tipo = models.ForeignKey(
        'humano.HumConceptoTipo', null=True, on_delete=models.PROTECT,
        related_name='conceptos_concepto_tipo_rel',
    )

    class Meta:
        db_table = 'hum_concepto'
        ordering = ['orden']
        verbose_name = 'Concepto'
        verbose_name_plural = 'Conceptos'

    def __str__(self):
        return self.nombre
