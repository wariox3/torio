from rest_framework import serializers

from general.models import GenDocumentoDetalle


class GenDocumentoDetalleInformeSerializer(serializers.ModelSerializer):
    """
    Serializer estándar (plano, solo lectura) para los informes sobre
    GenDocumentoDetalle. La invariante de cada informe la garantiza el ViewSet en
    `get_queryset`; aquí se define el contrato común de columnas y la whitelist de
    filtros/orden que consume `FiltrosDinamicosMixin`.
    """

    campos_filtrables = {
        'id',
        'documento_id',
        'item_id',
        'puesto_id',
        'modalidad_id',
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
        'puesto',
        'modalidad',
    )
    ordenamiento_default_lista = ('-documento__fecha', '-id')

    documento_numero = serializers.IntegerField(source='documento.numero', read_only=True)
    documento_fecha = serializers.DateField(source='documento.fecha', read_only=True)
    documento_tipo_id = serializers.IntegerField(source='documento.documento_tipo_id', read_only=True)
    documento_tipo_nombre = serializers.CharField(
        source='documento.documento_tipo.nombre', read_only=True, default=None,
    )
    contacto_id = serializers.IntegerField(source='documento.contacto_id', read_only=True)
    contacto_nombre = serializers.CharField(
        source='documento.contacto.nombre_corto', read_only=True, default=None,
    )
    item_nombre = serializers.CharField(source='item.nombre', read_only=True, default=None)
    puesto_nombre = serializers.CharField(source='puesto.nombre', read_only=True, default=None)
    modalidad_nombre = serializers.CharField(source='modalidad.nombre', read_only=True, default=None)
    modalidad_codigo = serializers.CharField(source='modalidad.codigo', read_only=True, default=None)

    class Meta:
        model = GenDocumentoDetalle
        fields = [
            'id',
            'documento_id',
            'documento_numero',
            'documento_fecha',
            'documento_tipo_id',
            'documento_tipo_nombre',
            'contacto_id',
            'contacto_nombre',
            'item_id',
            'item_nombre',
            'puesto_id',
            'puesto_nombre',
            'modalidad_id',
            'modalidad_nombre',
            'modalidad_codigo',
            'detalle',
            'cantidad',
            'precio',
            'total',
            'afectado',
            'pendiente',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
        ]


class GenDocumentoDetalleInformeExportarSerializer(serializers.Serializer):
    """Estructura estándar del Excel de los informes (usada por ExportarExcelMixin)."""

    model = GenDocumentoDetalle
    nombre_archivo = 'informe_documento_detalle'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('documento.numero', 'Documento'),
        ('documento.fecha', 'Fecha'),
        ('documento.documento_tipo.nombre', 'Tipo documento'),
        ('documento.contacto.nombre_corto', 'Contacto'),
        ('item.nombre', 'Item'),
        ('puesto.nombre', 'Puesto'),
        ('modalidad.nombre', 'Modalidad'),
        ('modalidad.codigo', 'Código modalidad'),
        ('detalle', 'Detalle'),
        ('cantidad', 'Cantidad'),
        ('precio', 'Precio'),
        ('total', 'Total'),
        ('afectado', 'Afectado'),
        ('pendiente', 'Pendiente'),
        ('horas', 'Horas'),
        ('horas_diurnas', 'Horas diurnas'),
        ('horas_nocturnas', 'Horas nocturnas'),
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
