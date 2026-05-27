from rest_framework import serializers

from contenedor.models import CtnMovimiento


class CtnMovimientoSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)

    class Meta:
        model = CtnMovimiento
        fields = ['id', 'evento_pago', 'tipo', 'concepto', 'valor', 'fecha', 'fecha_vence', 'cliente', 'cliente_nombre']
        read_only_fields = ['id', 'fecha']
