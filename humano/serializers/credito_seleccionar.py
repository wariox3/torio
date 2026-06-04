from rest_framework import serializers

from humano.models import HumCredito


class HumCreditoSeleccionarSerializer(serializers.ModelSerializer):
    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = HumCredito
        fields = ['id', 'contrato', 'contrato_nombre', 'total', 'saldo']
