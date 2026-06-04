from rest_framework import serializers

from humano.models import HumConcepto


class HumConceptoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConcepto
        fields = [
            'id', 'nombre', 'porcentaje', 'operacion', 'orden', 'adicional',
            'ingreso_base_prestacion', 'ingreso_base_prestacion_vacacion',
            'ingreso_base_cotizacion', 'concepto_tipo',
        ]
