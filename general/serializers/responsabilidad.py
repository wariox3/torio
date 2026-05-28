from rest_framework import serializers

from general.models import GenResponsabilidad


class GenResponsabilidadSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenResponsabilidad
        fields = ['id', 'nombre', 'codigo']
