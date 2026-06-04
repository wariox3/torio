from rest_framework import serializers

from humano.models import HumTiempo


class HumTiempoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumTiempo
        fields = ['id', 'nombre']
