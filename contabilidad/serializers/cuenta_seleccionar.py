from rest_framework import serializers

from contabilidad.models import ConCuenta


class ConCuentaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConCuenta
        fields = ['id', 'codigo', 'nombre']
