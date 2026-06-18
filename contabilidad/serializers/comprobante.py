from rest_framework import serializers

from contabilidad.models import ConComprobante


class ConComprobanteSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConComprobante
        fields = ['id', 'nombre', 'codigo']
