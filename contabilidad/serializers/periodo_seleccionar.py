from rest_framework import serializers

from contabilidad.models import ConPeriodo


class ConPeriodoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConPeriodo
        fields = ['id', 'anio', 'mes']
