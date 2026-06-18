from rest_framework import serializers

from general.models import GenEstado


class GenEstadoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenEstado
        fields = ['id', 'nombre', 'codigo']
