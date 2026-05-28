from django.db import models


class GenLog(models.Model):
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    accion = models.ForeignKey('general.GenAccion', on_delete=models.PROTECT)
    modelo = models.ForeignKey('general.GenModelo', on_delete=models.PROTECT)
    objeto_id = models.CharField(max_length=50, db_index=True)
    datos = models.JSONField(null=True)
    usuario_id = models.BigIntegerField(null=True, db_index=True)
    usuario_correo = models.CharField(max_length=255, null=True)

    class Meta:
        db_table = 'gen_log'
        ordering = ['-fecha']
        indexes = [models.Index(fields=['modelo', 'objeto_id'])]
        verbose_name = 'Log'
        verbose_name_plural = 'Logs'

    def __str__(self):
        return f'{self.fecha:%Y-%m-%d %H:%M} {self.accion_id} {self.modelo_id} #{self.objeto_id}'
