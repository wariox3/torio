from rest_framework import serializers

from humano.models import HumLiquidacion


class HumLiquidacionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato', 'fecha', 'estado_aprobado', 'estado_generado'}
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


class HumLiquidacionSeleccionarSerializer(serializers.ModelSerializer):
    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = HumLiquidacion
        fields = ['id', 'contrato', 'contrato_nombre', 'fecha', 'total']
