from rest_framework import serializers

from humano.models import HumLiquidacionAdicional
from humano.serializers.liquidacion import MENSAJE_LIQUIDACION_CERRADA


class HumLiquidacionAdicionalSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'liquidacion_id', 'concepto_id'}
    select_related_lista = ('liquidacion', 'concepto')
    ordenamiento_default_lista = ('-id',)

    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, default=None)

    class Meta:
        model = HumLiquidacionAdicional
        fields = ['id', 'adicional', 'deduccion', 'detalle', 'concepto', 'concepto_nombre', 'liquidacion']
        read_only_fields = ['id']

    def validate(self, attrs):
        adicional = attrs.get('adicional', 0)
        deduccion = attrs.get('deduccion', 0)
        if adicional < 0 or deduccion < 0:
            raise serializers.ValidationError('El adicional y la deducción no pueden ser negativos.')
        if not adicional and not deduccion:
            raise serializers.ValidationError('Indique un valor de adicional o de deducción.')
        # Generada, sus valores ya están en el documento: no entran adicionales nuevos.
        liquidacion = attrs['liquidacion']
        if liquidacion.estado_generado or liquidacion.estado_aprobado:
            raise serializers.ValidationError(MENSAJE_LIQUIDACION_CERRADA)
        return attrs
