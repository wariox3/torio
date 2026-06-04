from rest_framework import serializers

from humano.models import HumConceptoNomina


class HumConceptoNominaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConceptoNomina
        fields = ['id', 'nombre', 'concepto']
