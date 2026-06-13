from django.db import models


class TurSoporte(models.Model):
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    fecha_hasta_periodo = models.DateField()
    grupo = models.ForeignKey(
        'humano.HumGrupo',
        null=True,
        on_delete=models.PROTECT,
        related_name='soportes_grupo_rel',
    )

    class Meta:
        db_table = 'tur_soporte'
        ordering = ['fecha_desde', 'id']
        verbose_name = 'Soporte'
        verbose_name_plural = 'Soportes'

    def __str__(self):
        return f'{self.id} - {self.fecha_desde}'
