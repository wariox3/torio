from rest_framework import serializers

from humano.models import HumPeriodo


class HumPeriodoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumPeriodo
        fields = ['id', 'codigo', 'nombre', 'dias']
