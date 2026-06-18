from rest_framework import serializers

from general.models import GenImpuestoTipo


class GenImpuestoTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenImpuestoTipo
        fields = ['id', 'nombre', 'codigo']
