from rest_framework import serializers

from humano.models import HumNovedadTipo


class HumNovedadTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumNovedadTipo
        fields = ['id', 'nombre', 'novedad_clase_id', 'concepto', 'concepto2']
