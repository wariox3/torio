from django.db import models


class CtnPlan(models.Model):
    id = models.IntegerField(primary_key=True)
    nombre = models.CharField(max_length=50, null=True)
    limite_usuarios = models.IntegerField(default=0)
    usuarios_base = models.IntegerField(default=0)
    limite_ingresos = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    precio = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    precio_usuario_adicional = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    limite_electronicos = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    plan_tipo_id = models.CharField(max_length=1, null=True)
    orden = models.IntegerField(default=0)
    compra = models.BooleanField(default=False)
    tesoreria = models.BooleanField(default=False)
    venta = models.BooleanField(default=False)
    cartera = models.BooleanField(default=False)
    inventario = models.BooleanField(default=False)
    humano = models.BooleanField(default=False)
    contabilidad = models.BooleanField(default=False)

    class Meta:
        db_table = 'ctn_plan'
        ordering = ['-id']
