from rest_framework import serializers

from general.models import GenContacto


class GenContactoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de contactos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenContacto
    nombre_archivo = 'contactos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('identificacion.nombre', 'Tipo identificación'),
        ('numero_identificacion', 'Número identificación'),
        ('digito_verificacion', 'DV'),
        ('nombre_corto', 'Nombre corto'),
        ('nombre1', 'Primer nombre'),
        ('nombre2', 'Segundo nombre'),
        ('apellido1', 'Primer apellido'),
        ('apellido2', 'Segundo apellido'),
        ('direccion', 'Dirección'),
        ('ciudad.nombre', 'Ciudad'),
        ('tipo_persona.nombre', 'Tipo persona'),
        ('telefono', 'Teléfono'),
        ('celular', 'Celular'),
        ('correo', 'Correo'),
        ('cliente', 'Cliente'),
        ('proveedor', 'Proveedor'),
        ('empleado', 'Empleado'),
        ('conductor', 'Conductor'),
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
