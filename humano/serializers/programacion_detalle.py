from rest_framework import serializers

from humano.models import HumProgramacionDetalle


class HumProgramacionDetalleSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'programacion', 'contrato', 'ingreso', 'retiro'}
    select_related_lista = ('programacion', 'contrato', 'contrato__contacto')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = HumProgramacionDetalle
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'dias',
            'dias_transporte',
            'dias_novedad',
            'salario',
            'salario_promedio',
            'base_prestacion',
            'diurna',
            'nocturna',
            'festiva_diurna',
            'festiva_nocturna',
            'extra_diurna',
            'extra_nocturna',
            'extra_festiva_diurna',
            'extra_festiva_nocturna',
            'recargo_nocturno',
            'recargo_festivo_diurno',
            'recargo_festivo_nocturno',
            'pago_horas',
            'pago_auxilio_transporte',
            'pago_incapacidad',
            'pago_licencia',
            'pago_vacacion',
            'descuento_salud',
            'descuento_pension',
            'descuento_fondo_solidaridad',
            'descuento_retencion_fuente',
            'descuento_credito',
            'descuento_embargo',
            'adicional',
            'ingreso',
            'retiro',
            'error_terminacion',
            'base_cotizacion_acumulado',
            'devengado',
            'deduccion',
            'total',
            'deduccion_fondo_pension_acumulado',
            'prima_propuesto',
            'cesantia_propuesto',
            'interes_propuesto',
            'programacion',
            'contrato',
            'contrato_nombre',
        ]
        read_only_fields = ['id']
