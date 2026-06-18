from rest_framework import serializers

from general.models import GenPais


class GenPaisSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenPais
        fields = ['id', 'nombre', 'codigo']
