from rest_framework import serializers

from turno.models import TurPuesto


class TurPuestoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de puestos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = TurPuesto
    nombre_archivo = 'puestos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('direccion', 'Dirección'),
        ('celular', 'Celular'),
        ('contacto.nombre_corto', 'Contacto'),
        ('programador.nombre', 'Programador'),
        ('ciudad.nombre', 'Ciudad'),
        ('centro_costo.nombre', 'Centro de costo'),
        ('latitud', 'Latitud'),
        ('longitud', 'Longitud'),
        ('estado_inactivo', 'Inactivo'),
        ('comentario', 'Comentario'),
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
