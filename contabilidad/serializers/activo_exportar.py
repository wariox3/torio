from rest_framework import serializers

from contabilidad.models import ConActivo


class ConActivoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de activos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = ConActivo
    nombre_archivo = 'activos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('marca', 'Marca'),
        ('serie', 'Serie'),
        ('modelo', 'Modelo'),
        ('fecha_compra', 'Fecha compra'),
        ('fecha_activacion', 'Fecha activación'),
        ('fecha_baja', 'Fecha baja'),
        ('duracion', 'Duración'),
        ('valor_compra', 'Valor compra'),
        ('depreciacion_inicial', 'Depreciación inicial'),
        ('depreciacion_acumulada', 'Depreciación acumulada'),
        ('depreciacion_saldo', 'Depreciación saldo'),
        ('activo_grupo.nombre', 'Grupo activo'),
        ('metodo_depreciacion.nombre', 'Método depreciación'),
        ('cuenta_gasto.nombre', 'Cuenta gasto'),
        ('cuenta_depreciacion.nombre', 'Cuenta depreciación'),
        ('centro_costo.nombre', 'Centro de costo'),
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
