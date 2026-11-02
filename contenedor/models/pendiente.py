from django.db import models


class CtnPendiente(models.Model):
    """Un pendiente que el análisis encontró en un contenedor, para avisarle al usuario."""

    fecha = models.DateTimeField(auto_now_add=True)
    mensaje = models.CharField(max_length=200)
    cantidad = models.IntegerField(default=0, db_default=0)
    cliente = models.ForeignKey(
        'contenedor.CtnCliente', on_delete=models.CASCADE, related_name='pendientes',
    )
    pendiente_tipo = models.ForeignKey('contenedor.CtnPendienteTipo', on_delete=models.PROTECT)

    class Meta:
        db_table = 'ctn_pendiente'
        ordering = ['-id']
        verbose_name = 'Pendiente'
        verbose_name_plural = 'Pendientes'

    def __str__(self):
        return f'{self.pendiente_tipo_id} - {self.cliente_id}'
