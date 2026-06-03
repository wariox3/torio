from rest_framework import serializers

from general.models import GenSector


class GenSectorSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenSector
        fields = ['id', 'nombre', 'porcentaje', 'tipo']
