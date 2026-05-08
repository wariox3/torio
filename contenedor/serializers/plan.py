from rest_framework import serializers

from contenedor.models import CtnPlan


class CtnPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnPlan
        fields = [
            'id', 'nombre', 'limite_usuarios', 'usuarios_base',
            'limite_ingresos', 'precio', 'precio_usuario_adicional',
            'limite_electronicos', 'plan_tipo_id', 'orden',
            'compra', 'tesoreria', 'venta', 'cartera',
            'inventario', 'humano', 'contabilidad',
        ]


class CtnPlanListaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnPlan
        fields = ['id', 'nombre']
