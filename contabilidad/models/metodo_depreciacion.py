from django.db import models


class ConMetodoDepreciacion(models.Model):
    id = models.IntegerField(primary_key=True)
    nombre = models.CharField(max_length=100, null=True)

    class Meta:
        db_table = 'con_metodo_depreciacion'
        ordering = ['nombre']
        verbose_name = 'Método de depreciación'
        verbose_name_plural = 'Métodos de depreciación'

    def __str__(self):
        return self.nombre or str(self.id)
