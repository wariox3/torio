from rest_framework import serializers

from contabilidad.models import ConMovimiento


class ConMovimientoInformeSerializer(serializers.ModelSerializer):
    """
    Serializer estándar (plano, solo lectura) de los informes de `con_movimiento`
    con el estándar de `GenDocumentoInformeViewSet`: un renglón por movimiento.
    La invariante de cada informe la garantiza el ViewSet en `get_queryset`; aquí
    se define el contrato de columnas y la whitelist de filtros/orden que consume
    `FiltrosDinamicosMixin`.
    """

    campos_filtrables = {
        'id',
        'numero',
        'fecha',
        'periodo_id',
        'comprobante_id',
        'cuenta_id',
        'cuenta__codigo',
        'cuenta__nombre',
        'contacto_id',
        'contacto__nombre_corto',
        'contacto__numero_identificacion',
        'centro_costo_id',
        'documento_id',
        'naturaleza',
        'cierre',
        'saldo_inicial',
        'debito',
        'credito',
        'base',
        'detalle',
    }
    select_related_lista = ('comprobante', 'cuenta', 'contacto', 'centro_costo')
    ordenamiento_default_lista = ('-fecha', '-numero', '-id')

    comprobante_nombre = serializers.CharField(source='comprobante.nombre', read_only=True, allow_null=True)
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, allow_null=True)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, allow_null=True)
    contacto_numero_identificacion = serializers.CharField(
        source='contacto.numero_identificacion', read_only=True, allow_null=True,
    )
    contacto_nombre_corto = serializers.CharField(source='contacto.nombre_corto', read_only=True, allow_null=True)
    centro_costo_nombre = serializers.CharField(source='centro_costo.nombre', read_only=True, allow_null=True)

    class Meta:
        model = ConMovimiento
        fields = [
            'id',
            'numero',
            'fecha',
            'periodo_id',
            'comprobante_id',
            'comprobante_nombre',
            'cuenta_id',
            'cuenta_codigo',
            'cuenta_nombre',
            'contacto_id',
            'contacto_numero_identificacion',
            'contacto_nombre_corto',
            'centro_costo_id',
            'centro_costo_nombre',
            'documento_id',
            'naturaleza',
            'detalle',
            'debito',
            'credito',
            'base',
            'cierre',
        ]
        read_only_fields = fields


class ConMovimientoInformeExportarSerializer(serializers.Serializer):
    """Estructura estándar del Excel de los informes de movimiento (usada por ExportarExcelMixin)."""

    model = ConMovimiento
    nombre_archivo = 'informe_movimiento'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('periodo_id', 'Periodo'),
        ('comprobante.nombre', 'Comprobante'),
        ('cuenta.codigo', 'Código cuenta'),
        ('cuenta.nombre', 'Cuenta'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Tercero'),
        ('centro_costo.nombre', 'Centro de costo'),
        ('documento_id', 'Documento'),
        ('naturaleza', 'Naturaleza'),
        ('detalle', 'Detalle'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('base', 'Base'),
        ('cierre', 'Cierre'),
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
