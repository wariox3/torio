from rest_framework import serializers

from contabilidad.models import ConCuentaGrupo


class ConCuentaGrupoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConCuentaGrupo
        fields = ['id', 'nombre']
