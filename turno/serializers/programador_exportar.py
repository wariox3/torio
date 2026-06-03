from rest_framework import serializers

from turno.models import TurProgramador


class TurProgramadorExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de programadores.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = TurProgramador
    nombre_archivo = 'programadores'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
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
