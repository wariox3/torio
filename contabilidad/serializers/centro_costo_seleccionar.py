from rest_framework import serializers

from contabilidad.models import ConCentroCosto


class ConCentroCostoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConCentroCosto
        fields = ['id', 'nombre', 'codigo']
