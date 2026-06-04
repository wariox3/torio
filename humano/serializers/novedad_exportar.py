from rest_framework import serializers

from humano.models import HumNovedad


class HumNovedadExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de novedades.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumNovedad
    nombre_archivo = 'novedades'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('contrato.contacto.nombre_corto', 'Empleado'),
        ('novedad_tipo.nombre', 'Tipo novedad'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('dias', 'Días'),
        ('dias_disfrutados', 'Días disfrutados'),
        ('dias_dinero', 'Días dinero'),
        ('total', 'Total'),
        ('prorroga', 'Prórroga'),
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
