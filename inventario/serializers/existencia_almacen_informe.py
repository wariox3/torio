from rest_framework import serializers

from inventario.models import InvExistencia


class InvExistenciaAlmacenInformeSerializer(serializers.ModelSerializer):
    """
    Columnas del informe `existencia_almacen`: la fila es una `InvExistencia`, o
    sea el saldo de un item en un almacén.

    Es `existencia` una granularidad más abajo. Un item que se movió en dos
    almacenes sale dos veces, y la suma de sus filas es lo que el otro informe
    muestra en una sola: los dos saldos los escribe el mismo servicio en la misma
    transacción.

    El costo no está en el saldo sino en el item, y es el promedio ponderado de
    todos los almacenes: valorizar una fila usa el mismo costo para cada almacén,
    no un costo por almacén, que no existe.
    """

    campos_filtrables = {
        'id',
        'item_id',
        'item__codigo',
        'item__nombre',
        'item__referencia',
        'item__inventario',
        'item__negativo',
        'item__inactivo',
        'almacen_id',
        'almacen__nombre',
        'existencia',
        'remision',
        'disponible',
    }
    select_related_lista = ('item', 'almacen')
    ordenamiento_default_lista = ('almacen__nombre', 'item__nombre')

    item_codigo = serializers.CharField(source='item.codigo', read_only=True, default=None)
    item_nombre = serializers.CharField(source='item.nombre', read_only=True)
    item_referencia = serializers.CharField(
        source='item.referencia', read_only=True, default=None,
    )
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True)
    costo_promedio = serializers.DecimalField(
        source='item.costo_promedio', max_digits=20, decimal_places=6, read_only=True,
    )

    class Meta:
        model = InvExistencia
        fields = [
            'id',
            'item_id',
            'item_codigo',
            'item_nombre',
            'item_referencia',
            'almacen_id',
            'almacen_nombre',
            'existencia',
            'remision',
            'disponible',
            'costo_promedio',
        ]


class InvExistenciaAlmacenInformeExportarSerializer(serializers.Serializer):
    """Estructura del Excel de `existencia_almacen` (usada por ExportarExcelMixin)."""

    model = InvExistencia
    nombre_archivo = 'informe_existencia_almacen'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('item.codigo', 'Código'),
        ('item.nombre', 'Item'),
        ('item.referencia', 'Referencia'),
        ('almacen.nombre', 'Almacén'),
        ('existencia', 'Existencia'),
        ('remision', 'Remisión'),
        ('disponible', 'Disponible'),
        ('item.costo_promedio', 'Costo promedio'),
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
