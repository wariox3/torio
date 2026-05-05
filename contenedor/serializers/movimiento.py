from rest_framework import serializers

from contenedor.models import CtnMovimiento


class CtnMovimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnMovimiento
        fields = [
            'id', 'tipo', 'numero', 'concepto', 'valor', 'periodo',
            'estado', 'fecha_emision', 'fecha_vencimiento', 'movimiento_origen',
        ]
        read_only_fields = ['id', 'fecha_emision']
