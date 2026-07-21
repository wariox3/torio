from rest_framework import serializers

from general.models import GenDocumento


class GenDocumentoInformeSerializer(serializers.ModelSerializer):
    """
    Serializer estándar (plano, solo lectura) para los informes sobre GenDocumento.
    La invariante de cada informe la garantiza el ViewSet en `get_queryset`; aquí se
    define el contrato común de columnas y la whitelist de filtros/orden que consume
    `FiltrosDinamicosMixin`.
    """

    campos_filtrables = {
        'id',
        'numero',
        'fecha',
        'fecha_vence',
        'documento_tipo_id',
        'contacto_id',
        'contacto__nombre_corto',
        'contacto__numero_identificacion',
        'sector_id',
        'sede_id',
        'estado_aprobado',
        'estado_anulado',
        'estado_contabilizado',
    }
    select_related_lista = (
        'documento_tipo',
        'contacto',
        'sector',
        'sede',
        'plazo_pago',
        'metodo_pago',
        'forma_pago',
    )
    ordenamiento_default_lista = ('-fecha', '-numero')

    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    contacto_numero_identificacion = serializers.CharField(
        source='contacto.numero_identificacion', read_only=True, default=None,
    )
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True, default=None)
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, default=None)
    plazo_pago_nombre = serializers.CharField(source='plazo_pago.nombre', read_only=True, default=None)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True, default=None)
    forma_pago_nombre = serializers.CharField(source='forma_pago.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumento
        fields = [
            'id',
            'numero',
            'fecha',
            'fecha_vence',
            'documento_tipo_id',
            'documento_tipo_nombre',
            'contacto_id',
            'contacto_nombre',
            'contacto_numero_identificacion',
            'sector_id',
            'sector_nombre',
            'sede_id',
            'sede_nombre',
            'plazo_pago_id',
            'plazo_pago_nombre',
            'metodo_pago_id',
            'metodo_pago_nombre',
            'forma_pago_id',
            'forma_pago_nombre',
            'subtotal',
            'descuento',
            'impuesto',
            'total',
            'afectado',
            'pendiente',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
        ]


class GenDocumentoInformeExportarSerializer(serializers.Serializer):
    """Estructura estándar del Excel de los informes (usada por ExportarExcelMixin)."""

    model = GenDocumento
    nombre_archivo = 'informe_documento'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('fecha_vence', 'Fecha vence'),
        ('documento_tipo.nombre', 'Tipo documento'),
        ('contacto.nombre_corto', 'Contacto'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('sector.nombre', 'Sector'),
        ('sede.nombre', 'Sede'),
        ('plazo_pago.nombre', 'Plazo de pago'),
        ('metodo_pago.nombre', 'Método de pago'),
        ('forma_pago.nombre', 'Forma de pago'),
        ('subtotal', 'Subtotal'),
        ('descuento', 'Descuento'),
        ('impuesto', 'Impuesto'),
        ('total', 'Total'),
        ('afectado', 'Afectado'),
        ('pendiente', 'Pendiente'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_contabilizado', 'Contabilizado'),
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
