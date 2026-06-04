from rest_framework import serializers

from humano.models import HumProgramacion


class HumProgramacionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'nombre', 'grupo', 'pago_tipo', 'periodo',
        'estado_aprobado', 'estado_generado', 'fecha_desde', 'fecha_hasta',
    }
    select_related_lista = ('grupo', 'pago_tipo', 'periodo')
    ordenamiento_default_lista = ('-id',)

    grupo_nombre = serializers.CharField(source='grupo.nombre', read_only=True, default=None)
    pago_tipo_nombre = serializers.CharField(source='pago_tipo.nombre', read_only=True, default=None)
    periodo_nombre = serializers.CharField(source='periodo.nombre', read_only=True, default=None)

    class Meta:
        model = HumProgramacion
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'fecha_hasta_periodo',
            'nombre',
            'dias',
            'dias_reales',
            'contratos',
            'devengado',
            'deduccion',
            'total',
            'estado_aprobado',
            'estado_generado',
            'pago_horas',
            'pago_auxilio_transporte',
            'pago_incapacidad',
            'pago_licencia',
            'pago_vacacion',
            'pago_prima',
            'pago_cesantia',
            'pago_interes',
            'descuento_salud',
            'descuento_pension',
            'descuento_fondo_solidaridad',
            'descuento_retencion_fuente',
            'descuento_credito',
            'descuento_embargo',
            'adicional',
            'comentario',
            'base_prestacion_minimo',
            'base_prestacion_minimo_salario',
            'grupo',
            'grupo_nombre',
            'pago_tipo',
            'pago_tipo_nombre',
            'periodo',
            'periodo_nombre',
        ]
        read_only_fields = [
            'id',
            'dias_reales',
            'contratos',
            'devengado',
            'deduccion',
            'total',
            'estado_aprobado',
            'estado_generado',
        ]
