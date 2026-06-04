from rest_framework import serializers

from humano.models import HumCargo


class HumCargoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de cargos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumCargo
    nombre_archivo = 'cargos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('estado_inactivo', 'Inactivo'),
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
