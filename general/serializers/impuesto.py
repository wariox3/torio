from rest_framework import serializers

from general.models import GenImpuesto


class GenImpuestoSeleccionarSerializer(serializers.ModelSerializer):
    impuesto_tipo_nombre = serializers.CharField(source='impuesto_tipo.nombre', read_only=True, default=None)

    class Meta:
        model = GenImpuesto
        fields = [
            'id',
            'nombre',
            'nombre_extendido',
            'porcentaje',
            'porcentaje_base',
            'operacion',
            'venta',
            'compra',
            'impuesto_tipo',
            'impuesto_tipo_nombre',
        ]
