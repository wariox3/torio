from rest_framework import serializers

from general.models import GenPrecio


class GenPrecioSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenPrecio
        fields = ['id', 'nombre']
