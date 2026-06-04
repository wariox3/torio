from django.db import models


class HumGrupo(models.Model):
    nombre = models.CharField(max_length=100)
    periodo = models.ForeignKey(
        'humano.HumPeriodo', null=True, on_delete=models.PROTECT,
        related_name='grupos_periodo_rel',
    )

    class Meta:
        db_table = 'hum_grupo'
        ordering = ['nombre']
        verbose_name = 'Grupo'
        verbose_name_plural = 'Grupos'

    def __str__(self):
        return self.nombre
