from rest_framework import serializers

from contabilidad.models import ConCuenta


class ConCuentaExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de cuentas.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = ConCuenta
    nombre_archivo = 'cuentas'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('exige_base', 'Exige base'),
        ('exige_contacto', 'Exige contacto'),
        ('exige_grupo', 'Exige grupo'),
        ('permite_movimiento', 'Permite movimiento'),
        ('nivel', 'Nivel'),
        ('cuenta_clase.nombre', 'Clase'),
        ('cuenta_grupo.nombre', 'Grupo'),
        ('cuenta_cuenta.nombre', 'Cuenta'),
        ('cuenta_subcuenta.nombre', 'Subcuenta'),
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
