from rest_framework import serializers

from humano.models import HumLiquidacionAdicional


class HumLiquidacionAdicionalSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'liquidacion', 'concepto'}
    select_related_lista = ('liquidacion', 'concepto')
    ordenamiento_default_lista = ('-id',)

    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, default=None)

    class Meta:
        model = HumLiquidacionAdicional
        fields = ['id', 'adicional', 'deduccion', 'detalle', 'concepto', 'concepto_nombre', 'liquidacion']
        read_only_fields = ['id']
