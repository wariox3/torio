from rest_framework import serializers

from humano.models import HumAdicional


class HumAdicionalExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de adicionales.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumAdicional
    nombre_archivo = 'adicionales'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('contrato.contacto.nombre_corto', 'Empleado'),
        ('concepto.nombre', 'Concepto'),
        ('valor', 'Valor'),
        ('horas', 'Horas'),
        ('aplica_dia_laborado', 'Aplica día laborado'),
        ('permanente', 'Permanente'),
        ('inactivo', 'Inactivo'),
        ('detalle', 'Detalle'),
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
