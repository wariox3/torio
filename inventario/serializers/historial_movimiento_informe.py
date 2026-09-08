from rest_framework import serializers

from general.models import GenDocumentoDetalle


class InvHistorialMovimientoInformeSerializer(serializers.ModelSerializer):
    """
    Columnas del informe `historial_movimiento`: una fila por línea de documento
    que movió inventario.

    `cantidad_operada` ya viene con el signo del movimiento —negativo si sale—,
    así que es la columna que hay que sumar para reconstruir un saldo, no
    `cantidad`, que es siempre la cantidad digitada. Las dos salen porque no
    tienen por qué coincidir: la operada es la que el tipo de documento decidió
    aplicar al inventario.

    `operacion_inventario` y `operacion_remision` dicen cuál de los dos saldos
    movió la línea: una remisión saca de disponible sin sacar de existencia, y
    sin esas dos columnas las dos clases de movimiento se leerían igual.
    """

    campos_filtrables = {
        'id',
        'documento_id',
        'documento__numero',
        'documento__fecha',
        'documento__documento_tipo_id',
        'documento__contacto_id',
        'item_id',
        'item__codigo',
        'item__nombre',
        'almacen_id',
        'almacen__nombre',
        'contacto_id',
        'cantidad',
        'cantidad_operada',
        'costo',
        'precio',
        'operacion_inventario',
        'operacion_remision',
    }
    select_related_lista = (
        'documento',
        'documento__documento_tipo',
        'documento__contacto',
        'item',
        'almacen',
    )
    # El movimiento se lee del más reciente al más viejo; `id` desempata las
    # líneas del mismo documento, que comparten fecha y número.
    ordenamiento_default_lista = ('-documento__fecha', '-documento__numero', '-id')

    documento_numero = serializers.IntegerField(
        source='documento.numero', read_only=True, default=None,
    )
    documento_fecha = serializers.DateField(source='documento.fecha', read_only=True)
    documento_tipo_id = serializers.IntegerField(
        source='documento.documento_tipo_id', read_only=True,
    )
    documento_tipo_nombre = serializers.CharField(
        source='documento.documento_tipo.nombre', read_only=True,
    )
    contacto_nombre_corto = serializers.CharField(
        source='documento.contacto.nombre_corto', read_only=True, default=None,
    )
    item_codigo = serializers.CharField(source='item.codigo', read_only=True, default=None)
    item_nombre = serializers.CharField(source='item.nombre', read_only=True)
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True)

    class Meta:
        model = GenDocumentoDetalle
        fields = [
            'id',
            'documento_id',
            'documento_numero',
            'documento_fecha',
            'documento_tipo_id',
            'documento_tipo_nombre',
            'contacto_nombre_corto',
            'item_id',
            'item_codigo',
            'item_nombre',
            'almacen_id',
            'almacen_nombre',
            'cantidad',
            'cantidad_operada',
            'operacion_inventario',
            'operacion_remision',
            'costo',
            'precio',
            'detalle',
        ]


class InvHistorialMovimientoInformeExportarSerializer(serializers.Serializer):
    """Estructura del Excel de `historial_movimiento` (usada por ExportarExcelMixin)."""

    model = GenDocumentoDetalle
    nombre_archivo = 'informe_historial_movimiento'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('documento.fecha', 'Fecha'),
        ('documento.documento_tipo.nombre', 'Tipo documento'),
        ('documento.numero', 'Número'),
        ('documento.contacto.nombre_corto', 'Contacto'),
        ('item.codigo', 'Código'),
        ('item.nombre', 'Item'),
        ('almacen.nombre', 'Almacén'),
        ('cantidad', 'Cantidad'),
        ('cantidad_operada', 'Cantidad operada'),
        ('operacion_inventario', 'Operación inventario'),
        ('operacion_remision', 'Operación remisión'),
        ('costo', 'Costo'),
        ('precio', 'Precio'),
        ('detalle', 'Detalle'),
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
