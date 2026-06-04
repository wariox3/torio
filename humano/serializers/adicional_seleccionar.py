from rest_framework import serializers

from humano.models import HumAdicional


class HumAdicionalSeleccionarSerializer(serializers.ModelSerializer):
    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)
    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, default=None)

    class Meta:
        model = HumAdicional
        fields = ['id', 'contrato', 'contrato_nombre', 'concepto', 'concepto_nombre', 'valor']
