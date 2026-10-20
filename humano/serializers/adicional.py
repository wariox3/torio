from rest_framework import serializers

from humano.models import HumAdicional


class HumAdicionalSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato_id', 'concepto_id', 'programacion_id', 'inactivo', 'permanente'}
    select_related_lista = ('concepto', 'contrato', 'contrato__contacto', 'programacion')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, allow_null=True)
    contrato_contacto_id = serializers.IntegerField(source='contrato.contacto_id', read_only=True, allow_null=True)
    contrato_contacto_numero_identificacion = serializers.CharField(
        source='contrato.contacto.numero_identificacion', read_only=True, allow_null=True,
    )
    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, allow_null=True)
    programacion_nombre = serializers.CharField(source='programacion.nombre', read_only=True, allow_null=True)

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
            'contrato_contacto_id',
            'contrato_contacto_numero_identificacion',
        ]
        read_only_fields = ['id']
