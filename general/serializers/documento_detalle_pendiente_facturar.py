from rest_framework import serializers

from general.models import GenDocumentoDetalle


class GenDocumentoDetallePendienteFacturarSerializer(serializers.ModelSerializer):
    """
    Informe "pendiente por facturar": detalles con `pendiente > 0`.

    Serializer plano de solo lectura. La invariante `pendiente > 0` la garantiza
    el ViewSet en `get_queryset`; aquí solo se define el contrato de columnas y la
    whitelist de filtros/orden que consume `FiltrosDinamicosMixin`.
    """

    campos_filtrables = {
        'id',
        'documento_id',
        'item_id',
        'afectado',
        'pendiente',
        'documento__numero',
        'documento__fecha',
        'documento__documento_tipo_id',
        'documento__contacto_id',
    }
    select_related_lista = (
        'documento',
        'documento__documento_tipo',
        'documento__contacto',
        'item',
    )
    ordenamiento_default_lista = ('-documento__fecha', '-id')

    documento_numero = serializers.IntegerField(source='documento.numero', read_only=True)
    documento_fecha = serializers.DateField(source='documento.fecha', read_only=True)
    documento_tipo_nombre = serializers.CharField(
        source='documento.documento_tipo.nombre', read_only=True, default=None,
    )
    contacto_id = serializers.IntegerField(source='documento.contacto_id', read_only=True)
    contacto_nombre = serializers.CharField(
        source='documento.contacto.nombre_corto', read_only=True, default=None,
    )
    item_nombre = serializers.CharField(source='item.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumentoDetalle
        fields = [
            'id',
            'documento_id',
            'documento_numero',
            'documento_fecha',
            'documento_tipo_nombre',
            'contacto_id',
            'contacto_nombre',
            'item_id',
            'item_nombre',
            'detalle',
            'cantidad',
            'precio',
            'total',
            'afectado',
            'pendiente',
        ]


class GenDocumentoDetallePendienteFacturarExportarSerializer(serializers.Serializer):
    """Estructura del Excel del informe pendiente por facturar (usado por ExportarExcelMixin)."""

    model = GenDocumentoDetalle
    nombre_archivo = 'pendiente_por_facturar'
    hoja = 'Pendiente por facturar'

    campos_excel = (
        ('id', 'ID'),
        ('documento.numero', 'Documento'),
        ('documento.fecha', 'Fecha'),
        ('documento.documento_tipo.nombre', 'Tipo documento'),
        ('documento.contacto.nombre_corto', 'Contacto'),
        ('item.nombre', 'Item'),
        ('detalle', 'Detalle'),
        ('cantidad', 'Cantidad'),
        ('precio', 'Precio'),
        ('total', 'Total'),
        ('afectado', 'Afectado'),
        ('pendiente', 'Pendiente'),
    )

    @staticmethod
    def valor_excel(obj, campo):
        valor = obj
        for parte in campo.split('.'):
            if valor is None:
                return None
            valor = getattr(valor, parte, None)
        if isinstance(valor, bool):
            return 'Sí' if valor else 'No'
        return valor
