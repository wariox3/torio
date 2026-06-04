from rest_framework import serializers

from humano.models import HumTipoCotizante


class HumTipoCotizanteSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumTipoCotizante
        fields = ['id', 'codigo', 'nombre']
