from rest_framework import serializers

from humano.models import HumContratoTipo


class HumContratoTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumContratoTipo
        fields = ['id', 'nombre']
