from rest_framework import serializers

from humano.models import HumAdicional


class HumAdicionalSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'contrato_id', 'concepto_id', 'programacion_id', 'inactivo', 'permanente',
        'contrato__contacto__numero_identificacion', 'contrato__contacto__nombre_corto',
        'concepto__nombre',
    }
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

    # `permanente` no lo decide el front, sale de `programacion`: un adicional de una
    # programación se paga solo en esa nómina, y uno sin programación se paga en
    # todas hasta inactivarlo.

    def create(self, validated_data):
        validated_data['permanente'] = validated_data.get('programacion') is None
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Un PATCH que no trae `programacion` conserva la que tenía, y con ella
        # se recalcula: así un `permanente` suelto en el body tampoco lo cambia.
        programacion = validated_data.get('programacion', instance.programacion)
        validated_data['permanente'] = programacion is None
        return super().update(instance, validated_data)
