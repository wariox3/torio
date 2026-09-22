from django.db import models


class CtnEventoPago(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    evento = models.CharField(max_length=50, null=True)
    entorno = models.CharField(max_length=10, null=True)
    transaccion = models.CharField(max_length=50, null=True)
    metodo_pago = models.CharField(max_length=50, null=True)
    referencia = models.CharField(max_length=500, null=True)
    correo = models.CharField(max_length=250, null=True)
    estado = models.CharField(max_length=50, null=True)
    fecha_transaccion = models.DateTimeField(null=True)
    estado_aplicado = models.BooleanField(default=False, db_default=False)
    vr_original = models.DecimalField(max_digits=16, decimal_places=2, default=0, db_default=0)
    datos = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'ctn_evento_pago'
        verbose_name = 'Evento pago'
        verbose_name_plural = 'Eventos pago'
        constraints = [
            # Una transacción aprobada se aplica una sola vez: es lo que impide que
            # un evento reenviado —un reintento de Wompi o uno capturado, que
            # conserva su firma válida— extienda la suscripción otra vez. El
            # webhook lo revisa antes, pero dos entregas simultáneas pasarían las
            # dos esa revisión; esta es la que no se puede saltar. Los demás estados
            # (pendiente, rechazado) sí se pueden repetir: no aplican nada.
            models.UniqueConstraint(
                fields=['transaccion'],
                condition=models.Q(estado='APPROVED'),
                name='ctn_evento_pago_transaccion_aprobada_unica',
            ),
        ]

    def __str__(self):
        return f'{self.evento} - {self.transaccion} - {self.estado}'
