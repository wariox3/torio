from django.db import models


class GenAsesor(models.Model):
    nombre_corto = models.CharField(max_length=200)
    celular = models.CharField(max_length=50)
    correo = models.EmailField(max_length=255)

    class Meta:
        db_table = 'gen_asesor'
        ordering = ['nombre_corto']
        verbose_name = 'Asesor'
        verbose_name_plural = 'Asesores'

    def __str__(self):
        return self.nombre_corto
