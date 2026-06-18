from rest_framework import serializers

from general.models import GenDocumentoClase


class GenDocumentoClaseSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenDocumentoClase
        fields = ['id', 'nombre']
