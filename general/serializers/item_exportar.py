from rest_framework import serializers

from general.models import GenItem


class GenItemExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de items.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenItem
    nombre_archivo = 'items'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('codigo', 'Código'),
        ('referencia', 'Referencia'),
        ('costo', 'Costo'),
        ('precio', 'Precio'),
        ('producto', 'Producto'),
        ('servicio', 'Servicio'),
        ('inventario', 'Inventario'),
        ('negativo', 'Negativo'),
        ('favorito', 'Favorito'),
        ('venta', 'Venta'),
        ('inactivo', 'Inactivo'),
        ('existencia', 'Existencia'),
        ('cuenta_venta.nombre', 'Cuenta venta'),
        ('cuenta_compra.nombre', 'Cuenta compra'),
        ('cuenta_costo_venta.nombre', 'Cuenta costo venta'),
        ('cuenta_inventario.nombre', 'Cuenta inventario'),
        ('impuestos', 'Impuestos (IDs)'),
    )

    @staticmethod
    def valor_excel(obj, campo):
        """Devuelve el valor a escribir en la celda para `obj` y `campo`."""
        if campo == 'impuestos':
            # Ids y no nombres: es la única columna del archivo que el importador
            # puede volver a leer, y lo que él espera son ids. Con nombres el
            # ciclo exportar -> editar -> importar se cortaría acá.
            return ','.join(
                str(relacion.impuesto_id)
                for relacion in obj.items_impuestos_item_rel.all()
            )

        valor = obj
        for parte in campo.split('.'):
            if valor is None:
                return None
            valor = getattr(valor, parte, None)
        if isinstance(valor, bool):
            return 'Sí' if valor else 'No'
        return valor
