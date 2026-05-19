from rest_framework import serializers

from general.models import GenDocumento
from general.serializers.documento_detalle import GenDocumentoDetalleSerializer


class GenDocumentoSerializer(serializers.ModelSerializer):
    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True)
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True)

    class Meta:
        model = GenDocumento
        fields = [
            'id',
            'numero',
            'fecha',
            'fecha_contable',
            'fecha_vence',
            'fecha_desde',
            'fecha_hasta',
            'soporte',
            'orden_compra',
            'remision',
            'comentario',
            'documento_tipo',
            'documento_tipo_nombre',
            'contacto',
            'contacto_nombre',
            'resolucion',
            'plazo_pago',
            'asesor',
            'cuenta_banco',
            'comprobante',
            'cuenta',
            'sector',
            'sector_nombre',
            'documento_referencia',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
        ]
        read_only_fields = [
            'id',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
        ]


class GenDocumentoDetalleVistaSerializer(GenDocumentoSerializer):
    detalles = GenDocumentoDetalleSerializer(
        many=True,
        read_only=True,
        source='documentos_detalles_documento_rel',
    )

    class Meta(GenDocumentoSerializer.Meta):
        fields = GenDocumentoSerializer.Meta.fields + ['detalles']
