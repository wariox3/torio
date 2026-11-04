from django.db import models


class VenCaja(models.Model):
    """
    Una caja registradora del punto de venta. `placa`, `ubicacion` y `tipo` son
    los datos que el documento equivalente P.O.S. le informa a la DIAN (`PlacaCaja`,
    `UbicaciónCaja` y `TipoCaja`); la DIAN no los contrasta contra ningún registro.
    """

    nombre = models.CharField(max_length=100)
    placa = models.CharField(max_length=50, null=True)
    ubicacion = models.CharField(max_length=255, null=True)
    tipo = models.CharField(max_length=100, null=True)
    estado_activo = models.BooleanField(default=True, db_default=True)
    sede = models.ForeignKey(
        'general.GenSede',
        on_delete=models.PROTECT,
        related_name='cajas_sede_rel',
    )

    class Meta:
        db_table = 'ven_caja'
        ordering = ['nombre']
        verbose_name = 'Caja'
        verbose_name_plural = 'Cajas'

    def __str__(self):
        return self.nombre
