from rest_framework import serializers

from turno.models import TurPrototipo


class TurPrototipoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de prototipos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = TurPrototipo
    nombre_archivo = 'prototipos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('fecha', 'Fecha'),
        ('fecha_inicio', 'Fecha inicio'),
        ('documento_detalle.puesto.nombre', 'Puesto'),
        ('secuencia.nombre', 'Secuencia'),
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
