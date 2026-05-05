from django.db import models


class CtnEventoPasarela(models.Model):
    movimiento = models.ForeignKey(
        'contenedor.CtnMovimiento',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='eventos_pasarela',
    )
    fecha = models.DateTimeField(auto_now_add=True)
    evento = models.CharField(max_length=50, null=True)
    entorno = models.CharField(max_length=10, null=True)
    transaccion = models.CharField(max_length=50, null=True)
    metodo_pago = models.CharField(max_length=50, null=True)
    referencia = models.CharField(max_length=500, null=True)
    correo = models.CharField(max_length=250, null=True)
    estado = models.CharField(max_length=50, null=True)
    fecha_transaccion = models.DateTimeField(null=True)
    estado_aplicado = models.BooleanField(default=False)
    vr_original = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    datos = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'ctn_evento_pasarela'
        verbose_name = 'Evento pasarela'
        verbose_name_plural = 'Eventos pasarela'

    def __str__(self):
        return f'{self.evento} - {self.transaccion} - {self.estado}'
