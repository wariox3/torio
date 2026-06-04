from rest_framework import serializers

from humano.models import HumSubtipoCotizante


class HumSubtipoCotizanteSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumSubtipoCotizante
        fields = ['id', 'codigo', 'nombre']
