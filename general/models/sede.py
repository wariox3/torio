from django.db import models


class GenSede(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=50, null=True)
    centro_costo = models.ForeignKey(
        'contabilidad.ConCentroCosto',
        null=True,
        on_delete=models.PROTECT,
        related_name='sedes_centro_costo_rel',
    )

    class Meta:
        db_table = 'gen_sede'
        ordering = ['nombre']
        verbose_name = 'Sede'
        verbose_name_plural = 'Sedes'

    def __str__(self):
        return self.nombre
