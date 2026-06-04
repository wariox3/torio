from rest_framework import serializers

from humano.models import HumNovedad


class HumNovedadSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato', 'novedad_tipo', 'prorroga', 'fecha_desde', 'fecha_hasta'}
    select_related_lista = ('contrato', 'contrato__contacto', 'novedad_tipo', 'novedad_referencia')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)
    novedad_tipo_nombre = serializers.CharField(source='novedad_tipo.nombre', read_only=True, default=None)

    class Meta:
        model = HumNovedad
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'fecha_desde_periodo',
            'fecha_hasta_periodo',
            'fecha_desde_empresa',
            'fecha_hasta_empresa',
            'fecha_desde_entidad',
            'fecha_hasta_entidad',
            'dias_disfrutados',
            'dias_disfrutados_reales',
            'dias_dinero',
            'pago_disfrute',
            'dias',
            'dias_empresa',
            'dias_entidad',
            'pago_dinero',
            'pago_dia_disfrute',
            'pago_dia_dinero',
            'base_cotizacion_propuesto',
            'base_cotizacion',
            'hora_empresa',
            'hora_entidad',
            'pago_empresa',
            'pago_entidad',
            'total',
            'dias_acumulados',
            'prorroga',
            'detalle',
            'contrato',
            'contrato_nombre',
            'novedad_tipo',
            'novedad_tipo_nombre',
            'novedad_referencia',
        ]
        read_only_fields = [
            'id',
            'dias_disfrutados_reales',
            'pago_disfrute',
            'dias_empresa',
            'dias_entidad',
            'pago_dinero',
            'pago_dia_disfrute',
            'pago_dia_dinero',
            'base_cotizacion_propuesto',
            'base_cotizacion',
            'hora_empresa',
            'hora_entidad',
            'pago_empresa',
            'pago_entidad',
            'total',
            'dias_acumulados',
        ]
