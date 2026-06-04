from rest_framework import serializers

from humano.models import HumConfiguracionProvision


class HumConfiguracionProvisionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConfiguracionProvision
        fields = ['id', 'tipo', 'orden', 'tipo_costo', 'cuenta_debito', 'cuenta_credito']
