from rest_framework import serializers

from humano.models import HumConceptoTipo


class HumConceptoTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConceptoTipo
        fields = ['id', 'nombre']
