from rest_framework import serializers

from humano.models import HumLiquidacion

MENSAJE_LIQUIDACION_CERRADA = (
    'La liquidación está generada o aprobada: desgenérela antes de modificarla.'
)


class HumLiquidacionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato_id', 'fecha', 'estado_aprobado', 'estado_generado'}
    select_related_lista = ('contrato', 'contrato__contacto')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = HumLiquidacion
        fields = [
            'id',
            'fecha',
            'fecha_desde',
            'fecha_hasta',
            'dias',
            'dias_cesantia',
            'dias_prima',
            'dias_vacacion',
            'cesantia',
            'interes',
            'prima',
            'vacacion',
            'deduccion',
            'adicion',
            'total',
            'salario',
            'fecha_ultimo_pago',
            'fecha_ultimo_pago_prima',
            'fecha_ultimo_pago_cesantia',
            'fecha_ultimo_pago_vacacion',
            'estado_aprobado',
            'estado_generado',
            'comentario',
            'contrato',
            'contrato_nombre',
        ]
        read_only_fields = [
            'id',
            'dias',
            'dias_cesantia',
            'dias_prima',
            'dias_vacacion',
            'cesantia',
            'interes',
            'prima',
            'vacacion',
            'deduccion',
            'adicion',
            'total',
            'salario',
            'estado_aprobado',
            'estado_generado',
        ]

    def validate(self, attrs):
        # Generada, sus valores ya están en el documento: editarla los descuadraría.
        if self.instance is not None and (self.instance.estado_generado or self.instance.estado_aprobado):
            raise serializers.ValidationError(MENSAJE_LIQUIDACION_CERRADA)
        return attrs


class HumLiquidacionSeleccionarSerializer(serializers.ModelSerializer):
    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = HumLiquidacion
        fields = ['id', 'contrato', 'contrato_nombre', 'fecha', 'total']
