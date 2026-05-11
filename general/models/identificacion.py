from django.db import models


class GenIdentificacion(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    abreviatura = models.CharField(max_length=10, null=True)
    orden = models.BigIntegerField(default=0)
    codigo = models.CharField(max_length=10, null=True)
    aporte = models.CharField(max_length=10, null=True)
    pais = models.ForeignKey('general.GenPais', null=True, on_delete=models.PROTECT)
    tipo_persona = models.ForeignKey('general.GenTipoPersona', null=True, on_delete=models.PROTECT)

    class Meta:
        db_table = 'gen_identificacion'
        ordering = ['orden', 'nombre']
        verbose_name = 'Identificación'
        verbose_name_plural = 'Identificaciones'

    def __str__(self):
        return self.nombre
