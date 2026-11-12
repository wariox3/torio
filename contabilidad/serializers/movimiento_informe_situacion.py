from rest_framework import serializers

_IMPORTE = {'max_digits': 20, 'decimal_places': 6, 'read_only': True}


class ConMovimientoInformeSituacionFormalFilaSerializer(serializers.Serializer):
    """
    Una fila del estado de situación financiera formal
    (`servicios.situacion_financiera.estado`).

    `tipo` dice cómo se pinta:

        SECCION       ACTIVO, PASIVO, PATRIMONIO; sin importes
        SUBSECCION    corriente / no corriente; sin importes
        LINEA         una cuenta (4 dígitos) o un grupo (2), según `nivel`
        RESULTADO     el resultado del ejercicio dentro del patrimonio: clases
                      4 a 7 más el grupo 36, acumulados al corte
        SUBTOTAL      total corriente / no corriente
        TOTAL         total activo / pasivo / patrimonio (doble subrayado)
        TOTAL_FINAL   total pasivo y patrimonio (doble subrayado)

    Cada sección viene en positivo en su naturaleza; una cuenta correctora (la
    depreciación acumulada) sale negativa. `anterior`, `variacion` y
    `porcentaje` son nulos sin comparativo. `porcentaje` es una fracción
    (0.25 = 25 %) sobre el valor absoluto del corte anterior, nula si está en cero.
    """

    tipo = serializers.CharField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    actual = serializers.DecimalField(**_IMPORTE, allow_null=True)
    anterior = serializers.DecimalField(**_IMPORTE, allow_null=True)
    variacion = serializers.DecimalField(**_IMPORTE, allow_null=True)
    porcentaje = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True, allow_null=True)


class ConMovimientoInformeSituacionFormalCorteSerializer(serializers.Serializer):
    """
    Resumen de un corte: los totales, si cuadra y las razones.

    `cuadrado` es activo = pasivo + patrimonio y `diferencia` lo que falta
    (activo − pasivo − patrimonio); lo descuadra un documento que no cuadra o un
    filtro dinámico. `razon_corriente` (activo corriente / pasivo corriente) y
    `endeudamiento` (pasivo / activo, fracción) son nulos si el divisor es cero.
    """

    activo = serializers.DecimalField(**_IMPORTE)
    activo_corriente = serializers.DecimalField(**_IMPORTE)
    activo_no_corriente = serializers.DecimalField(**_IMPORTE)
    pasivo = serializers.DecimalField(**_IMPORTE)
    pasivo_corriente = serializers.DecimalField(**_IMPORTE)
    pasivo_no_corriente = serializers.DecimalField(**_IMPORTE)
    patrimonio = serializers.DecimalField(**_IMPORTE)
    pasivo_patrimonio = serializers.DecimalField(**_IMPORTE)
    cuadrado = serializers.BooleanField(read_only=True)
    diferencia = serializers.DecimalField(**_IMPORTE)
    capital_trabajo = serializers.DecimalField(**_IMPORTE)
    razon_corriente = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True, allow_null=True)
    endeudamiento = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True, allow_null=True)


class ConMovimientoInformeSituacionFormalEncabezadoSerializer(serializers.Serializer):
    """Lo que va encima del estado: la empresa, los dos cortes y su resumen."""

    empresa = serializers.CharField(read_only=True)
    nit = serializers.CharField(read_only=True)
    fecha_corte = serializers.DateField(read_only=True)
    fecha_anterior = serializers.DateField(read_only=True, allow_null=True)
    comparar = serializers.CharField(read_only=True)
    nivel = serializers.CharField(read_only=True)
    actual = ConMovimientoInformeSituacionFormalCorteSerializer(read_only=True)
    anterior = ConMovimientoInformeSituacionFormalCorteSerializer(read_only=True, allow_null=True)


class ConMovimientoInformeSituacionFormalSerializer(serializers.Serializer):
    """Respuesta de `lista/` con `informe=formal`: encabezado y filas, sin paginar."""

    encabezado = ConMovimientoInformeSituacionFormalEncabezadoSerializer(read_only=True)
    filas = ConMovimientoInformeSituacionFormalFilaSerializer(many=True, read_only=True)
