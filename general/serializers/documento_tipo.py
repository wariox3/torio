from rest_framework import serializers

from general.models import GenDocumentoTipo


class GenDocumentoTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenDocumentoTipo
        fields = ['id', 'nombre']
