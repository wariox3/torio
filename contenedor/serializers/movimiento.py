from rest_framework import serializers

from contenedor.models import CtnMovimiento


class CtnMovimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnMovimiento
        fields = ['id', 'evento_pago', 'tipo', 'concepto', 'valor', 'fecha', 'fecha_vence']
        read_only_fields = ['id', 'fecha']
