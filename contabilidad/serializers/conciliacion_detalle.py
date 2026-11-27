from rest_framework import serializers

from contabilidad.models import ConConciliacionDetalle


class ConConciliacionDetalleSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'conciliacion_id', 'cuenta_id', 'documento_id', 'movimiento_id', 'estado_conciliado',
        'contacto_id', 'contacto__nombre_corto', 'contacto__numero_identificacion',
    }
    select_related_lista = ('conciliacion', 'cuenta', 'contacto', 'documento__documento_tipo')
    ordenamiento_default_lista = ('-id',)

    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, allow_null=True)
    contacto_nombre_corto = serializers.CharField(source='contacto.nombre_corto', read_only=True, allow_null=True)
    documento_numero = serializers.IntegerField(source='documento.numero', read_only=True, allow_null=True)
    documento_documento_tipo_nombre = serializers.CharField(
        source='documento.documento_tipo.nombre', read_only=True, allow_null=True,
    )

    class Meta:
        model = ConConciliacionDetalle
        fields = [
            'id',
            'fecha',
            'debito',
            'credito',
            'detalle',
            'estado_conciliado',
            'conciliacion',
            'cuenta',
            'cuenta_nombre',
            'contacto',
            'contacto_nombre_corto',
            'documento',
            'documento_numero',
            'documento_documento_tipo_nombre',
            'movimiento',
        ]
        read_only_fields = ['id']
