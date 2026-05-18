from django.db import models


class CtnIdentificacion(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    orden = models.BigIntegerField(default=0, db_default=0)
    codigo = models.CharField(max_length=10, null=True)
    pais = models.ForeignKey('contenedor.CtnPais', on_delete=models.CASCADE, null=True, related_name='identificaciones')

    class Meta:
        db_table = 'ctn_identificacion'
