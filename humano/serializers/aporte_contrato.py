from rest_framework import serializers

from humano.models import HumAporteContrato


class HumAporteContratoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'aporte', 'contrato', 'ingreso', 'retiro'}
    select_related_lista = ('aporte', 'contrato', 'contrato__contacto')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = HumAporteContrato
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'dias',
            'salario',
            'base_cotizacion',
            'cotizacion_pension',
            'cotizacion_pension_total',
            'cotizacion_pension_empresa',
            'cotizacion_pension_empleado',
            'cotizacion_voluntario_pension_afiliado',
            'cotizacion_voluntario_pension_aportante',
            'cotizacion_solidaridad_solidaridad',
            'cotizacion_solidaridad_subsistencia',
            'cotizacion_salud',
            'cotizacion_salud_empresa',
            'cotizacion_salud_empleado',
            'cotizacion_riesgos',
            'cotizacion_caja',
            'cotizacion_sena',
            'cotizacion_icbf',
            'cotizacion_total',
            'ingreso',
            'retiro',
            'error_terminacion',
            'aporte',
            'contrato',
            'contrato_nombre',
            'ciudad_labora',
            'entidad_salud',
            'entidad_pension',
            'entidad_caja',
            'entidad_riesgo',
            'entidad_sena',
            'entidad_icbf',
            'riesgo',
        ]
        read_only_fields = ['id']
