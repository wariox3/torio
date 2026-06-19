from rest_framework import serializers

from general.models import GenAsesor


class GenAsesorExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de asesores.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenAsesor
    nombre_archivo = 'asesores'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre_corto', 'Nombre corto'),
        ('celular', 'Celular'),
        ('correo', 'Correo'),
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
