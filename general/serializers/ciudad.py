from rest_framework import serializers

from general.models import GenCiudad


class GenCiudadSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenCiudad
        fields = ['id', 'nombre']
