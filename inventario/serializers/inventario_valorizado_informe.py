from rest_framework import serializers

from general.models import GenItem
from inventario.serializers.existencia_informe import InvExistenciaInformeSerializer


class InvInventarioValorizadoInformeSerializer(InvExistenciaInformeSerializer):
    """
    Columnas del informe `inventario_valorizado`: las mismas filas de
    `existencia` con lo que vale cada saldo.

    `costo_total` es `costo_promedio * existencia` y lo mantiene
    `_afectar_inventario` al aprobar una entrada; sale como columna y no se
    recalcula acá, para que el informe muestre lo que hay en la base y no una
    valorización propia que podría no coincidir con la contabilidad.

    Por eso mismo el costo que vale es `costo_promedio` (el ponderado, que es con
    el que se descarga la salida) y no `costo`, que es el de reposición que
    alguien teclea en la ficha del item. Los dos salen para poder compararlos.
    """

    campos_filtrables = InvExistenciaInformeSerializer.campos_filtrables | {
        'costo',
        'costo_promedio',
        'costo_total',
        'precio',
        'cuenta_inventario_id',
    }
    select_related_lista = ('cuenta_inventario',)

    cuenta_inventario_nombre = serializers.CharField(
        source='cuenta_inventario.nombre', read_only=True, default=None,
    )

    class Meta:
        model = GenItem
        fields = InvExistenciaInformeSerializer.Meta.fields + [
            'costo',
            'costo_promedio',
            'costo_total',
            'precio',
            'cuenta_inventario_id',
            'cuenta_inventario_nombre',
        ]


class InvInventarioValorizadoInformeExportarSerializer(serializers.Serializer):
    """Estructura del Excel de `inventario_valorizado` (usada por ExportarExcelMixin)."""

    model = GenItem
    nombre_archivo = 'informe_inventario_valorizado'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('referencia', 'Referencia'),
        ('existencia', 'Existencia'),
        ('remision', 'Remisión'),
        ('disponible', 'Disponible'),
        ('costo', 'Costo'),
        ('costo_promedio', 'Costo promedio'),
        ('costo_total', 'Costo total'),
        ('precio', 'Precio'),
        ('cuenta_inventario.nombre', 'Cuenta inventario'),
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
