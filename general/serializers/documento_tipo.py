from rest_framework import serializers

from general.models import GenDocumentoTipo


class GenDocumentoTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenDocumentoTipo
        fields = ['id', 'nombre']


class GenDocumentoTipoSerializer(serializers.ModelSerializer):
    """Lectura del tipo completo, para la pantalla que edita su configuración."""

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'nombre', 'consecutivo', 'documento_clase',
        'venta', 'compra', 'cobrar', 'pagar',
    }
    ordenamiento_default_lista = ('nombre',)
    select_related_lista = ('documento_clase', 'resolucion', 'cuenta_cobrar', 'cuenta_pagar', 'comprobante')

    documento_clase_nombre = serializers.CharField(source='documento_clase.nombre', read_only=True, default=None)
    resolucion_numero = serializers.CharField(source='resolucion.numero', read_only=True, default=None)
    cuenta_cobrar_codigo = serializers.CharField(source='cuenta_cobrar.codigo', read_only=True, default=None)
    cuenta_cobrar_nombre = serializers.CharField(source='cuenta_cobrar.nombre', read_only=True, default=None)
    cuenta_pagar_codigo = serializers.CharField(source='cuenta_pagar.codigo', read_only=True, default=None)
    cuenta_pagar_nombre = serializers.CharField(source='cuenta_pagar.nombre', read_only=True, default=None)
    comprobante_nombre = serializers.CharField(source='comprobante.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumentoTipo
        fields = [
            'id',
            'nombre',
            'consecutivo',
            'formato',
            'venta',
            'compra',
            'cobrar',
            'pagar',
            'electronico',
            'contabilidad',
            'inventario',
            'pos',
            'operacion',
            'operacion_inventario',
            'operacion_remision',
            'afecta_cantidad',
            'documento_clase',
            'documento_clase_nombre',
            'resolucion',
            'resolucion_numero',
            'cuenta_cobrar',
            'cuenta_cobrar_codigo',
            'cuenta_cobrar_nombre',
            'cuenta_pagar',
            'cuenta_pagar_codigo',
            'cuenta_pagar_nombre',
            'comprobante',
            'comprobante_nombre',
        ]
        # Solo se editan los tres de `GenDocumentoTipoActualizarSerializer`; el
        # resto describe la naturaleza del tipo y viene del fixture.
        read_only_fields = fields


class GenDocumentoTipoActualizarSerializer(serializers.ModelSerializer):
    """
    Lo único configurable por tenant de un catálogo que por lo demás es normativo:
    su numeración y las contrapartidas de cartera de su plan de cuentas.

    Los demás campos no son escribibles porque no están acá, no por una regla
    aparte: lo que no se declara, DRF lo ignora.
    """

    consecutivo = serializers.IntegerField(min_value=1)

    class Meta:
        model = GenDocumentoTipo
        fields = ['id', 'consecutivo', 'cuenta_cobrar', 'cuenta_pagar']
        read_only_fields = ['id']
