from rest_framework import serializers

from general.models import GenModalidad


class GenModalidadSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenModalidad
        fields = ['id', 'nombre', 'codigo', 'porcentaje_comercial', 'porcentaje_residencial']
