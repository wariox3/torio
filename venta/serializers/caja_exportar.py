from rest_framework import serializers

from venta.models import VenCaja


class VenCajaExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de cajas.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = VenCaja
    nombre_archivo = 'cajas'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('placa', 'Placa'),
        ('ubicacion', 'Ubicación'),
        ('tipo', 'Tipo'),
        ('estado_activo', 'Activo'),
        ('sede.id', 'Sede'),
        ('sede.nombre', 'Sede nombre'),
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
