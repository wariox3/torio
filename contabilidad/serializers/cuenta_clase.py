from rest_framework import serializers

from contabilidad.models import ConCuentaClase


class ConCuentaClaseSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConCuentaClase
        fields = ['id', 'nombre']
