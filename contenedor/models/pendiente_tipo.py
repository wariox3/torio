from django.db import models


class CtnPendienteTipo(models.Model):
    """Qué busca el análisis de pendientes en cada contenedor (periodo anterior abierto...)."""

    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=200)
    aplicacion = models.ForeignKey('contenedor.CtnAplicacion', on_delete=models.PROTECT)

    class Meta:
        db_table = 'ctn_pendiente_tipo'
        ordering = ['id']
        verbose_name = 'Tipo de pendiente'
        verbose_name_plural = 'Tipos de pendiente'

    def __str__(self):
        return self.nombre
