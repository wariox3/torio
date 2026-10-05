from rest_framework import serializers

from humano.models import HumAporteEntidad


class HumAporteEntidadExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de lo que el aporte le debe a
    cada entidad.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumAporteEntidad
    nombre_archivo = 'aporte_entidades'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('aporte.id', 'Aporte'),
        ('tipo', 'Tipo'),
        ('entidad.id', 'Entidad'),
        ('entidad.numero_identificacion', 'Identificación'),
        ('entidad.nombre', 'Nombre'),
        ('cotizacion', 'Cotización'),
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
