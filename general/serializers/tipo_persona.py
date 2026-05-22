from rest_framework import serializers

from general.models import GenTipoPersona


class GenTipoPersonaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenTipoPersona
        fields = ['id', 'nombre']
