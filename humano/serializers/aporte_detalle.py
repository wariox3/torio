from rest_framework import serializers

from humano.models import HumAporteDetalle


class HumAporteDetalleSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'aporte_contrato'}
    select_related_lista = ('aporte_contrato',)
    ordenamiento_default_lista = ('-id',)

    class Meta:
        model = HumAporteDetalle
        fields = [
            'id',
            'horas',
            'dias_pension',
            'dias_salud',
            'dias_riesgos',
            'dias_caja',
            'dias_incapacidad_laboral',
            'base_cotizacion_pension',
            'base_cotizacion_salud',
            'base_cotizacion_riesgos',
            'base_cotizacion_caja',
            'base_cotizacion_otros_parafiscales',
            'tarifa_pension',
            'tarifa_salud',
            'tarifa_riesgos',
            'tarifa_caja',
            'tarifa_sena',
            'tarifa_icbf',
            'cotizacion_pension',
            'cotizacion_voluntario_pension_afiliado',
            'cotizacion_voluntario_pension_aportante',
            'cotizacion_solidaridad_solidaridad',
            'cotizacion_solidaridad_subsistencia',
            'total_cotizacion_pension',
            'cotizacion_salud',
            'cotizacion_riesgos',
            'cotizacion_caja',
            'cotizacion_sena',
            'cotizacion_icbf',
            'cotizacion_total',
            'upc_adicional',
            'fecha_ingreso',
            'fecha_retiro',
            'fecha_inicio_variacion_permanente_salario',
            'fecha_inicio_suspension_temporal_contrato',
            'fecha_fin_suspension_temporal_contrato',
            'fecha_inicio_incapacidad_general',
            'fecha_fin_incapacidad_general',
            'fecha_inicio_licencia_maternidad',
            'fecha_fin_licencia_maternidad',
            'fecha_inicio_vacaciones',
            'fecha_fin_vacaciones',
            'fecha_inicio_incapacidad_laboral',
            'fecha_fin_incapacidad_laboral',
            'ingreso',
            'retiro',
            'variacion_permanente_salario',
            'variacion_transitoria_salario',
            'suspension_temporal_contrato',
            'incapacidad_general',
            'licencia_maternidad',
            'vacaciones',
            'licencia_remunerada',
            'aporte_voluntario_pension',
            'variacion_centro_trabajo',
            'salario_integral',
            'aporte_contrato',
        ]
        read_only_fields = ['id']
