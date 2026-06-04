from rest_framework import serializers

from humano.models import HumAporte


class HumAporteSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'anio', 'mes', 'presentacion', 'estado_aprobado', 'estado_generado', 'sucursal',
    }
    select_related_lista = ('sucursal', 'entidad_riesgo', 'entidad_sena', 'entidad_icbf')
    ordenamiento_default_lista = ('-id',)

    sucursal_nombre = serializers.CharField(source='sucursal.nombre', read_only=True, default=None)
    entidad_riesgo_nombre = serializers.CharField(source='entidad_riesgo.nombre', read_only=True, default=None)
    entidad_sena_nombre = serializers.CharField(source='entidad_sena.nombre', read_only=True, default=None)
    entidad_icbf_nombre = serializers.CharField(source='entidad_icbf.nombre', read_only=True, default=None)

    class Meta:
        model = HumAporte
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'fecha_hasta_periodo',
            'anio',
            'anio_salud',
            'mes',
            'mes_salud',
            'presentacion',
            'contratos',
            'empleados',
            'lineas',
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
            'estado_aprobado',
            'estado_generado',
            'comentario',
            'sucursal',
            'sucursal_nombre',
            'entidad_riesgo',
            'entidad_riesgo_nombre',
            'entidad_sena',
            'entidad_sena_nombre',
            'entidad_icbf',
            'entidad_icbf_nombre',
        ]
        read_only_fields = [
            'id',
            'contratos',
            'empleados',
            'lineas',
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
            'estado_aprobado',
            'estado_generado',
        ]


class HumAporteSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumAporte
        fields = ['id', 'anio', 'mes', 'presentacion']
