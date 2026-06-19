from rest_framework import serializers

from contabilidad.models import ConMovimiento


class ConMovimientoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de movimientos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = ConMovimiento
    nombre_archivo = 'movimientos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('comprobante.nombre', 'Comprobante'),
        ('cuenta.codigo', 'Código cuenta'),
        ('cuenta.nombre', 'Cuenta'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('base', 'Base'),
        ('naturaleza', 'Naturaleza'),
        ('detalle', 'Detalle'),
        ('centro_costo.nombre', 'Centro de costo'),
        ('contacto.nombre_corto', 'Tercero'),
    )

    @staticmethod
    def valor_excel(obj, campo):
        """Devuelve el valor a escribir en la celda para `obj` y `campo`."""
        valor = obj
        for parte in campo.split('.'):
            if valor is None:
                return None
            valor = getattr(valor, parte, None)
        if isinstance(valor, bool):
            return 'Sí' if valor else 'No'
        return valor
