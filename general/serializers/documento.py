from django.db import transaction
from rest_framework import serializers

from general.models import (
    GenDocumento,
    GenDocumentoTipo,
)
from general.serializers.documento_detalle import GenDocumentoDetalleSerializer
from general.servicios import crear_detalle


class GenDocumentoSerializer(serializers.ModelSerializer):
    campos_filtrables = {'id', 'numero', 'fecha', 'documento_tipo_id', 'contacto_id', 'contacto__nombre_corto', 'contacto__numero_identificacion', 'estado_aprobado', 'estado_anulado', 'estado_contabilizado'}
    select_related_lista = ('documento_tipo', 'contacto', 'sector')
    ordenamiento_default_lista = ('-fecha', '-numero')

    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    tercero_numero_identificacion = serializers.CharField(source='contacto.numero_identificacion', read_only=True, default=None)
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True, default=None)

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
            'tercero_numero_identificacion',
            'resolucion',
            'plazo_pago',
            'metodo_pago',
            'asesor',
            'cuenta_banco',
            'comprobante',
            'cuenta',
            'sector',
            'sector_nombre',
            'estrato',
            'documento_referencia',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'salario',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
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


class GenDocumentoCrearSerializer(GenDocumentoSerializer):
    detalles = GenDocumentoDetalleSerializer(
        many=True,
        required=False,
        source='documentos_detalles_documento_rel',
    )

    class Meta(GenDocumentoSerializer.Meta):
        fields = GenDocumentoSerializer.Meta.fields + ['detalles']

    @transaction.atomic
    def create(self, validated_data):
        detalles_data = validated_data.pop('documentos_detalles_documento_rel', [])
        documento = GenDocumento.objects.create(**validated_data)
        for detalle_data in detalles_data:
            crear_detalle(documento, detalle_data)
        documento.recalcular_totales()
        documento.save()
        return documento


class GenDocumentoGenerarSerializer(serializers.Serializer):
    documento_tipo_id = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(),
    )
    documento_tipo_id_destino = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(),
    )
    documento_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True,
    )
    anio = serializers.IntegerField(min_value=1900, max_value=9999)
    mes = serializers.IntegerField(min_value=1, max_value=12)
