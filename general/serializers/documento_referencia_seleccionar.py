from rest_framework import serializers

from general.models import GenDocumento


class GenDocumentoReferenciaSeleccionarSerializer(serializers.ModelSerializer):
    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    resolucion_prefijo = serializers.CharField(
        source='resolucion.prefijo', read_only=True, default=None,
    )

    class Meta:
        model = GenDocumento
        fields = [
            'id', 'numero', 'fecha', 'fecha_vence', 'total', 'afectado', 'pendiente', 'cue',
            'documento_tipo_id', 'documento_tipo_nombre', 'resolucion_prefijo',
        ]
