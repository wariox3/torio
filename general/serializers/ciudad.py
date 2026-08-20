from rest_framework import serializers

from general.models import GenCiudad


class GenCiudadSeleccionarSerializer(serializers.ModelSerializer):
    departamento_nombre = serializers.CharField(source='estado.nombre', read_only=True)

    class Meta:
        model = GenCiudad
        fields = ['id', 'nombre', 'departamento_nombre']
