from rest_framework import serializers


class ConMovimientoInformeResultadoFormalFilaSerializer(serializers.Serializer):
    """
    Una fila del estado de resultados formal (`servicios.estado_resultados.filas`).

    `tipo` dice cómo se pinta: `SECCION` es el título y no trae importes,
    `CUENTA` el detalle a 4 dígitos, `TOTAL` el cierre de la sección y
    `UTILIDAD` lo acumulado hasta ahí. Cada sección viene en positivo en su
    naturaleza; solo una utilidad puede ser negativa, y es pérdida.

    `porcentaje` es una fracción (0.25 = 25 %) sobre el valor absoluto del año
    anterior, y es nulo cuando ese año está en cero.
    """

    tipo = serializers.CharField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    actual = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True, allow_null=True)
    anterior = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True, allow_null=True)
    variacion = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True, allow_null=True)
    porcentaje = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True, allow_null=True)


class ConMovimientoInformeResultadoFormalEncabezadoSerializer(serializers.Serializer):
    """Lo que va encima del estado: la empresa y los dos cortes que se comparan."""

    empresa = serializers.CharField(read_only=True)
    fecha_desde = serializers.DateField(read_only=True)
    fecha_hasta = serializers.DateField(read_only=True)
    fecha_desde_anterior = serializers.DateField(read_only=True)
    fecha_hasta_anterior = serializers.DateField(read_only=True)


class ConMovimientoInformeResultadoFormalSerializer(serializers.Serializer):
    """Respuesta de `lista/` con `informe=formal`: encabezado y filas, sin paginar."""

    encabezado = ConMovimientoInformeResultadoFormalEncabezadoSerializer(read_only=True)
    filas = ConMovimientoInformeResultadoFormalFilaSerializer(many=True, read_only=True)
