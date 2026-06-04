from rest_framework import serializers

from contabilidad.models import ConActivoGrupo


class ConActivoGrupoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConActivoGrupo
        fields = ['id', 'nombre']
