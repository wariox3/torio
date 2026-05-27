from django.db import models


class CtnMovimiento(models.Model):
    evento_pago = models.OneToOneField(
        'contenedor.CtnEventoPago',
        on_delete=models.PROTECT,
        related_name='movimiento',
    )
    contacto = models.ForeignKey(
        'contenedor.CtnContacto',
        on_delete=models.PROTECT,
        related_name='movimientos',
    )
    cliente = models.ForeignKey(
        'contenedor.CtnCliente',
        null=True,
        on_delete=models.SET_NULL,
        related_name='movimientos',
    )
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.PROTECT,
        related_name='movimientos',
    )
    tipo = models.CharField(max_length=20)
    concepto = models.CharField(max_length=255)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    fecha = models.DateField(auto_now_add=True)
    fecha_vence = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'ctn_movimiento'
        verbose_name = 'Movimiento'
        verbose_name_plural = 'Movimientos'

    def __str__(self):
        return f'{self.id} - {self.usuario}'
