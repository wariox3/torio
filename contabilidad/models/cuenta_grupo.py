from django.db import models


class ConCuentaGrupo(models.Model):
    id = models.IntegerField(primary_key=True)
    nombre = models.CharField(max_length=100, null=True)

    class Meta:
        db_table = 'con_cuenta_grupo'
        ordering = ['id']
        verbose_name = 'Grupo de cuenta'
        verbose_name_plural = 'Grupos de cuenta'

    def __str__(self):
        return self.nombre or str(self.id)
