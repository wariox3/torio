from rest_framework import serializers

from contabilidad.models import ConCuentaCuenta


class ConCuentaCuentaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConCuentaCuenta
        fields = ['id', 'nombre']
