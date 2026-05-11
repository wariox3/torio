from django.db import models


class CtnSuscripcion(models.Model):
    cliente = models.ForeignKey(
        'contenedor.CtnCliente',
        on_delete=models.CASCADE,
        related_name='suscripciones',
    )
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.PROTECT,
        related_name='suscripciones',
    )
    suscripcion_tipo = models.ForeignKey(
        'contenedor.CtnSuscripcionTipo',
        null=True,
        on_delete=models.PROTECT,
        related_name='suscripciones',
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    FRECUENCIA_MENSUAL = 'M'
    FRECUENCIA_ANUAL = 'A'
    FRECUENCIA_PRUEBA = 'P'
    FRECUENCIA_CHOICES = [
        (FRECUENCIA_MENSUAL, 'Mensual'),
        (FRECUENCIA_ANUAL, 'Anual'),
        (FRECUENCIA_PRUEBA, 'Prueba'),
    ]
    frecuencia = models.CharField(max_length=1, choices=FRECUENCIA_CHOICES, default=FRECUENCIA_MENSUAL)

    class Meta:
        db_table = 'ctn_suscripcion'
        verbose_name = 'Suscripción'
        verbose_name_plural = 'Suscripciones'

    def __str__(self):
        return f'{self.cliente} ({self.fecha_inicio} → {self.fecha_fin})'
