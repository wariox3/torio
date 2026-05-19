from django.db import models


class GenSector(models.Model):
    class Tipo(models.TextChoices):
        COMERCIAL = 'C', 'Comercial'
        RESIDENCIAL = 'R', 'Residencial'

    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100, null=True)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    tipo = models.CharField(
        max_length=1,
        choices=Tipo.choices,
        default=Tipo.RESIDENCIAL,
        db_default=Tipo.RESIDENCIAL,
    )

    class Meta:
        db_table = 'gen_sector'
        ordering = ['nombre']
        verbose_name = 'Sector'
        verbose_name_plural = 'Sectores'

    def __str__(self):
        return self.nombre or ''
