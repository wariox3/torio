from rest_framework import serializers

from humano.models import HumGrupo


class HumGrupoSeleccionarSerializer(serializers.ModelSerializer):
    periodo_dias = serializers.IntegerField(source='periodo.dias', read_only=True, allow_null=True)

    class Meta:
        model = HumGrupo
        fields = ['id', 'nombre', 'periodo_dias']
