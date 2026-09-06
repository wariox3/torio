from rest_framework import serializers

from general.models import GenItem


class InvExistenciaInformeSerializer(serializers.ModelSerializer):
    """
    Columnas del informe `existencia`: una fila por item, con el saldo
    consolidado de todos los almacenes.

    Los tres saldos son los del item, no los de un almacén: quien los mueve
    (`general.servicios.documento._afectar_inventario`) escribe en la misma
    transacción la fila de `InvExistencia` del almacén y el acumulado del item, y
    este informe lee el segundo. Abrirlo por almacén es `existencia_almacen`.

    Acá no hay costo: cantidades y nada más. La valorización es
    `inventario_valorizado`, que es este mismo informe con las columnas de costo.
    """

    campos_filtrables = {
        'id',
        'nombre',
        'codigo',
        'referencia',
        'producto',
        'servicio',
        'inventario',
        'negativo',
        'favorito',
        'venta',
        'inactivo',
        'existencia',
        'remision',
        'disponible',
    }
    ordenamiento_default_lista = ('nombre',)

    class Meta:
        model = GenItem
        fields = [
            'id',
            'codigo',
            'nombre',
            'referencia',
            'existencia',
            'remision',
            'disponible',
            'negativo',
            'inactivo',
        ]


class InvExistenciaInformeExportarSerializer(serializers.Serializer):
    """Estructura del Excel de `existencia` (usada por ExportarExcelMixin)."""

    model = GenItem
    nombre_archivo = 'informe_existencia'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('referencia', 'Referencia'),
        ('existencia', 'Existencia'),
        ('remision', 'Remisión'),
        ('disponible', 'Disponible'),
        ('negativo', 'Permite negativo'),
        ('inactivo', 'Inactivo'),
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
