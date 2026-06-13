from django.db import models
from django.db.models.functions import Now
from django.utils import timezone


class TurPrototipo(models.Model):
    fecha = models.DateTimeField(default=timezone.now, db_default=Now())
    fecha_inicio = models.DateField()
    documento_detalle = models.ForeignKey(
        'general.GenDocumentoDetalle',
        on_delete=models.PROTECT,
        related_name='prototipos_documento_detalle_rel',
    )
    secuencia = models.ForeignKey(
        'turno.TurSecuencia',
        null=True,
        on_delete=models.PROTECT,
        related_name='prototipos_secuencia_rel',
    )

    class Meta:
        db_table = 'tur_prototipo'
        ordering = ['fecha', 'id']
        verbose_name = 'Prototipo'
        verbose_name_plural = 'Prototipos'

    def __str__(self):
        return f'{self.id} - {self.fecha_inicio}'
