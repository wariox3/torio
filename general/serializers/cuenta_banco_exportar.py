from rest_framework import serializers

from general.models import GenCuentaBanco


class GenCuentaBancoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de cuentas bancarias.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenCuentaBanco
    nombre_archivo = 'cuentas_bancarias'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('numero_cuenta', 'Número cuenta'),
        ('cuenta_banco_tipo.nombre', 'Cuenta banco tipo'),
        ('cuenta_banco_clase.nombre', 'Cuenta banco clase'),
        ('cuenta.nombre', 'Cuenta contable'),
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
