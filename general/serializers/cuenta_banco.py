from rest_framework import serializers

from general.models import GenCuentaBanco


class GenCuentaBancoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'nombre', 'numero_cuenta',
        'cuenta_banco_tipo', 'cuenta_banco_clase', 'cuenta',
    }
    select_related_lista = ('cuenta_banco_tipo', 'cuenta_banco_clase', 'cuenta')
    ordenamiento_default_lista = ('nombre',)

    cuenta_banco_tipo_nombre = serializers.CharField(
        source='cuenta_banco_tipo.nombre', read_only=True, default=None,
    )
    cuenta_banco_clase_nombre = serializers.CharField(
        source='cuenta_banco_clase.nombre', read_only=True, default=None,
    )
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, default=None)

    class Meta:
        model = GenCuentaBanco
        fields = [
            'id',
            'nombre',
            'numero_cuenta',
            'cuenta_banco_tipo',
            'cuenta_banco_tipo_nombre',
            'cuenta_banco_clase',
            'cuenta_banco_clase_nombre',
            'cuenta',
            'cuenta_nombre',
        ]
        read_only_fields = ['id']


class GenCuentaBancoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenCuentaBanco
        fields = ['id', 'nombre']
