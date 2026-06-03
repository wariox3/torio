from django.db import models


class TurPuesto(models.Model):
    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=100, null=True)
    celular = models.CharField(max_length=50, null=True)
    latitud = models.DecimalField(max_digits=11, decimal_places=8, null=True)
    longitud = models.DecimalField(max_digits=11, decimal_places=8, null=True)
    comentario = models.TextField(null=True)
    estado_inactivo = models.BooleanField(default=False, db_default=False)
    contacto = models.ForeignKey(
        'general.GenContacto', null=True, on_delete=models.PROTECT,
        related_name='puestos_contacto_rel',
    )
    programador = models.ForeignKey(
        'turno.TurProgramador', null=True, on_delete=models.PROTECT,
        related_name='puestos_programador_rel',
    )
    ciudad = models.ForeignKey(
        'general.GenCiudad', null=True, on_delete=models.PROTECT,
        related_name='puestos_ciudad_rel',
    )
    centro_costo = models.ForeignKey(
        'contabilidad.ConCentroCosto', null=True, on_delete=models.PROTECT,
        related_name='puestos_centro_costo_rel',
    )

    class Meta:
        db_table = 'tur_puesto'
        ordering = ['nombre']
        verbose_name = 'Puesto'
        verbose_name_plural = 'Puestos'

    def __str__(self):
        return self.nombre
