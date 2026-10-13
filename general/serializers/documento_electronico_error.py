from rest_framework import serializers

from general.models import GenDocumentoElectronicoError


class GenDocumentoElectronicoErrorSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'documento_id', 'fase', 'fecha'}
    ordenamiento_default_lista = ('id',)

    class Meta:
        model = GenDocumentoElectronicoError
        fields = ['id', 'documento', 'fase', 'mensaje', 'fecha']
        read_only_fields = fields
