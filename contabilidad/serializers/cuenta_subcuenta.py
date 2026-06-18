from rest_framework import serializers

from contabilidad.models import ConCuentaSubcuenta


class ConCuentaSubcuentaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConCuentaSubcuenta
        fields = ['id', 'nombre']
