from django.db import models


class CtnMovimiento(models.Model):
    TIPO_FACTURA = 'factura'
    TIPO_RECIBO = 'recibo'
    TIPO_CHOICES = [
        (TIPO_FACTURA, 'Factura'),
        (TIPO_RECIBO, 'Recibo'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_PAGADA = 'pagada'
    ESTADO_VENCIDA = 'vencida'
    ESTADO_ANULADA = 'anulada'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PAGADA, 'Pagada'),
        (ESTADO_VENCIDA, 'Vencida'),
        (ESTADO_ANULADA, 'Anulada'),
    ]

    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.PROTECT,
        related_name='movimientos',
    )
    movimiento_origen = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recibos',
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    numero = models.CharField(max_length=20, unique=True)
    concepto = models.CharField(max_length=255)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    periodo = models.DateField(help_text='Primer día del mes que cubre el movimiento')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'ctn_movimiento'
        verbose_name = 'Movimiento'
        verbose_name_plural = 'Movimientos'

    def __str__(self):
        return f'{self.numero} - {self.usuario}'
