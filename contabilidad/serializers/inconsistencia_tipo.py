from rest_framework import serializers

from contabilidad.models import ConInconsistenciaTipo


class ConInconsistenciaTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConInconsistenciaTipo
        fields = ['id', 'nombre', 'resolver_automatico']
