from rest_framework import serializers

from humano.models import HumAdicional


class HumAdicionalSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato', 'concepto', 'programacion', 'inactivo', 'permanente'}
    select_related_lista = ('concepto', 'contrato', 'contrato__contacto', 'programacion')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)
    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, default=None)
    programacion_nombre = serializers.CharField(source='programacion.nombre', read_only=True, default=None)

    class Meta:
        model = HumAdicional
        fields = [
            'id',
            'valor',
            'horas',
            'aplica_dia_laborado',
            'inactivo',
            'permanente',
            'detalle',
            'programacion',
            'programacion_nombre',
            'concepto',
            'concepto_nombre',
            'contrato',
            'contrato_nombre',
        ]
        read_only_fields = ['id']
