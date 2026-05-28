from decimal import Decimal

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
    frecuencia = models.CharField(max_length=1, choices=FRECUENCIA_CHOICES, default=FRECUENCIA_MENSUAL, db_default=FRECUENCIA_MENSUAL)
    precio = models.DecimalField(max_digits=14, decimal_places=2, default=0, db_default=0)
    referencia_pago = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'ctn_suscripcion'
        verbose_name = 'Suscripción'
        verbose_name_plural = 'Suscripciones'

    def save(self, *args, **kwargs):
        if self.suscripcion_tipo_id:
            from contenedor.models.suscripcion_tipo import CtnSuscripcionTipo
            precio_mensual = CtnSuscripcionTipo.objects.values_list(
                'precio', flat=True,
            ).get(pk=self.suscripcion_tipo_id)
            if self.frecuencia == self.FRECUENCIA_ANUAL:
                self.precio = precio_mensual * Decimal('0.9')
            else:
                self.precio = precio_mensual
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and 'precio' not in update_fields and (
                'suscripcion_tipo' in update_fields or 'frecuencia' in update_fields
            ):
                kwargs['update_fields'] = list(update_fields) + ['precio']
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.cliente} ({self.fecha_inicio} → {self.fecha_fin})'
