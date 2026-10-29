from rest_framework import serializers

from contabilidad.models import ConInconsistencia


class ConInconsistenciaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'periodo_id', 'inconsistencia_tipo_id', 'comprobante_id', 'movimiento_id', 'documento_id',
    }
    select_related_lista = (
        'inconsistencia_tipo', 'comprobante', 'movimiento__cuenta', 'documento__documento_tipo',
    )
    ordenamiento_default_lista = ('id',)

    inconsistencia_tipo_nombre = serializers.CharField(
        source='inconsistencia_tipo.nombre', read_only=True,
    )
    inconsistencia_tipo_resolver_automatico = serializers.BooleanField(
        source='inconsistencia_tipo.resolver_automatico', read_only=True,
    )
    comprobante_nombre = serializers.CharField(
        source='comprobante.nombre', read_only=True, allow_null=True,
    )
    movimiento_cuenta_codigo = serializers.CharField(
        source='movimiento.cuenta.codigo', read_only=True, allow_null=True,
    )
    documento_documento_tipo_nombre = serializers.CharField(
        source='documento.documento_tipo.nombre', read_only=True, allow_null=True,
    )

    class Meta:
        model = ConInconsistencia
        fields = [
            'id',
            'numero',
            'descripcion',
            'fecha',
            'inconsistencia_tipo',
            'inconsistencia_tipo_nombre',
            'inconsistencia_tipo_resolver_automatico',
            'periodo',
            'comprobante',
            'comprobante_nombre',
            'movimiento',
            'movimiento_cuenta_codigo',
            'documento',
            'documento_documento_tipo_nombre',
        ]
        read_only_fields = fields
