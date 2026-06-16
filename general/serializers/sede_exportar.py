from rest_framework import serializers

from general.models import GenSede


class GenSedeExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de sedes.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenSede
    nombre_archivo = 'sedes'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('codigo', 'Código'),
        ('centro_costo.codigo', 'Centro costo código'),
        ('centro_costo.nombre', 'Centro costo'),
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
