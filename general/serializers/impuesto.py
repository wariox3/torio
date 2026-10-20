from rest_framework import serializers

from general.models import GenImpuesto


class GenImpuestoSeleccionarSerializer(serializers.ModelSerializer):
    impuesto_tipo_nombre = serializers.CharField(source='impuesto_tipo.nombre', read_only=True, allow_null=True)
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, allow_null=True)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, allow_null=True)

    class Meta:
        model = GenImpuesto
        fields = [
            'id',
            'nombre',
            'nombre_extendido',
            'porcentaje',
            'porcentaje_base',
            'operacion',
            'venta',
            'compra',
            'impuesto_tipo',
            'impuesto_tipo_nombre',
            'cuenta',
            'cuenta_codigo',
            'cuenta_nombre',
        ]


class GenImpuestoSerializer(serializers.ModelSerializer):
    """Lectura del impuesto completo, para la pantalla que configura su cuenta."""

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'nombre', 'nombre_extendido', 'venta', 'compra', 'impuesto_tipo_id', 'cuenta_id',
    }
    ordenamiento_default_lista = ('id',)
    select_related_lista = ('impuesto_tipo', 'cuenta')

    impuesto_tipo_nombre = serializers.CharField(source='impuesto_tipo.nombre', read_only=True, allow_null=True)
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, allow_null=True)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, allow_null=True)

    class Meta:
        model = GenImpuesto
        fields = [
            'id',
            'nombre',
            'nombre_extendido',
            'porcentaje',
            'porcentaje_base',
            'operacion',
            'venta',
            'compra',
            'impuesto_tipo',
            'impuesto_tipo_nombre',
            'cuenta',
            'cuenta_codigo',
            'cuenta_nombre',
        ]
        # Solo la cuenta se edita, por `GenImpuestoActualizarSerializer`; el resto
        # es normativo y viene del catálogo.
        read_only_fields = fields


class GenImpuestoActualizarSerializer(serializers.ModelSerializer):
    """
    Lo único configurable por tenant del impuesto: la cuenta contable donde se
    registra. Lo que no se declara acá, DRF lo ignora.
    """

    class Meta:
        model = GenImpuesto
        fields = ['id', 'cuenta']
        read_only_fields = ['id']
