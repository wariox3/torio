from rest_framework import serializers

from general.models import GenContacto


class GenContactoSeleccionarSerializer(serializers.ModelSerializer):
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)
    plazo_pago_dias = serializers.IntegerField(source='plazo_pago.dias', read_only=True, default=None)
    plazo_pago_proveedor_dias = serializers.IntegerField(
        source='plazo_pago_proveedor.dias', read_only=True, default=None,
    )

    class Meta:
        model = GenContacto
        fields = [
            'id', 'nombre_corto', 'numero_identificacion',
            'direccion', 'correo', 'ciudad', 'ciudad_nombre', 'telefono',
            'precio_id', 'plazo_pago_id', 'plazo_pago_proveedor_id',
            'plazo_pago_dias', 'plazo_pago_proveedor_dias',
        ]
