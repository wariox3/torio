from rest_framework import serializers

from contabilidad.models import ConCuenta
from humano.models import HumConfiguracionProvision


class HumConfiguracionProvisionSerializer(serializers.ModelSerializer):
    """
    Configuración de provisiones con los nombres de sus FK, para la pantalla de
    configuración. Es un catálogo: tipo, orden y tipo de costo los fija torio, y el
    cliente solo elige las cuentas (el JSON no las trae, así que recargarlo no las pisa).
    """

    select_related_lista = ('tipo_costo', 'cuenta_debito', 'cuenta_credito')

    cuenta_debito = serializers.PrimaryKeyRelatedField(queryset=ConCuenta.objects.all(), allow_null=True)
    cuenta_credito = serializers.PrimaryKeyRelatedField(queryset=ConCuenta.objects.all(), allow_null=True)

    tipo_costo_nombre = serializers.CharField(source='tipo_costo.nombre', read_only=True, allow_null=True)
    cuenta_debito_codigo = serializers.CharField(source='cuenta_debito.codigo', read_only=True, allow_null=True)
    cuenta_debito_nombre = serializers.CharField(source='cuenta_debito.nombre', read_only=True, allow_null=True)
    cuenta_credito_codigo = serializers.CharField(source='cuenta_credito.codigo', read_only=True, allow_null=True)
    cuenta_credito_nombre = serializers.CharField(source='cuenta_credito.nombre', read_only=True, allow_null=True)

    class Meta:
        model = HumConfiguracionProvision
        fields = [
            'id', 'tipo', 'orden',
            'tipo_costo', 'tipo_costo_nombre',
            'cuenta_debito', 'cuenta_debito_codigo', 'cuenta_debito_nombre',
            'cuenta_credito', 'cuenta_credito_codigo', 'cuenta_credito_nombre',
        ]
        read_only_fields = [
            campo for campo in fields if campo not in ('cuenta_debito', 'cuenta_credito')
        ]

    def _cuenta_con_movimiento(self, cuenta):
        # Las cuentas de agrupación (clase, grupo, mayor) no reciben movimiento.
        if cuenta is not None and not cuenta.permite_movimiento:
            raise serializers.ValidationError(f'La cuenta {cuenta.codigo} no permite movimientos.')
        return cuenta

    def validate_cuenta_debito(self, cuenta):
        return self._cuenta_con_movimiento(cuenta)

    def validate_cuenta_credito(self, cuenta):
        return self._cuenta_con_movimiento(cuenta)


class HumConfiguracionProvisionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConfiguracionProvision
        fields = ['id', 'tipo', 'orden', 'tipo_costo', 'cuenta_debito', 'cuenta_credito']
