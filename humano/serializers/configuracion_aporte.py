from rest_framework import serializers

from contabilidad.models import ConCuenta
from humano.models import HumConfiguracionAporte


class HumConfiguracionAporteSerializer(serializers.ModelSerializer):
    """
    Configuración de aportes con los datos de su cuenta, para la pantalla de
    configuración. Es un catálogo: tipo y orden los fija torio, y el cliente solo
    elige la cuenta (el JSON no la trae, así que recargarlo no la pisa).
    """

    select_related_lista = ('cuenta',)

    cuenta = serializers.PrimaryKeyRelatedField(queryset=ConCuenta.objects.all(), allow_null=True)

    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, allow_null=True)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, allow_null=True)

    class Meta:
        model = HumConfiguracionAporte
        fields = ['id', 'tipo', 'orden', 'cuenta', 'cuenta_codigo', 'cuenta_nombre']
        read_only_fields = [campo for campo in fields if campo != 'cuenta']

    def validate_cuenta(self, cuenta):
        # Las cuentas de agrupación (clase, grupo, mayor) no reciben movimiento.
        if cuenta is not None and not cuenta.permite_movimiento:
            raise serializers.ValidationError(f'La cuenta {cuenta.codigo} no permite movimientos.')
        return cuenta


class HumConfiguracionAporteSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConfiguracionAporte
        fields = ['id', 'tipo', 'orden', 'cuenta']
