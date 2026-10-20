from rest_framework import serializers

from contabilidad.models import ConMovimiento


class ConMovimientoSeleccionarSerializer(serializers.ModelSerializer):
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, allow_null=True)

    class Meta:
        model = ConMovimiento
        fields = ['id', 'numero', 'fecha', 'cuenta', 'cuenta_nombre', 'debito', 'credito']
