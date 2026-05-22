from rest_framework import serializers

from general.models import GenAsesor


class GenAsesorSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenAsesor
        fields = ['id', 'nombre_corto']
