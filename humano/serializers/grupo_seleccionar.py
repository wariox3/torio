from rest_framework import serializers

from humano.models import HumGrupo


class HumGrupoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumGrupo
        fields = ['id', 'nombre']
