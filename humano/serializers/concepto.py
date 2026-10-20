from rest_framework import serializers

from humano.models import HumConcepto


class HumConceptoSerializer(serializers.ModelSerializer):
    """Lista (solo lectura) del catálogo de conceptos de nómina."""

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'nombre', 'porcentaje', 'operacion', 'orden', 'adicional',
        'ingreso_base_prestacion', 'ingreso_base_prestacion_vacacion',
        'ingreso_base_cotizacion', 'concepto_tipo_id',
    }
    select_related_lista = ('concepto_tipo',)
    ordenamiento_default_lista = ('orden', 'id')

    concepto_tipo_nombre = serializers.CharField(source='concepto_tipo.nombre', read_only=True, allow_null=True)

    class Meta:
        model = HumConcepto
        fields = [
            'id', 'nombre', 'porcentaje', 'operacion', 'orden', 'adicional',
            'ingreso_base_prestacion', 'ingreso_base_prestacion_vacacion',
            'ingreso_base_cotizacion', 'concepto_tipo', 'concepto_tipo_nombre',
        ]
        read_only_fields = fields


class HumConceptoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConcepto
        fields = [
            'id', 'nombre', 'porcentaje', 'operacion', 'orden', 'adicional',
            'ingreso_base_prestacion', 'ingreso_base_prestacion_vacacion',
            'ingreso_base_cotizacion', 'concepto_tipo',
        ]
