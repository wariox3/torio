from rest_framework import serializers

from humano.models import HumCargo


class HumCargoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumCargo
        fields = ['id', 'codigo', 'nombre']
