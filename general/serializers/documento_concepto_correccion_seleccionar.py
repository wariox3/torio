from rest_framework import serializers

from general.models import GenDocumentoConceptoCorreccion


class GenDocumentoConceptoCorreccionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenDocumentoConceptoCorreccion
        fields = ['id', 'nombre', 'codigo']
