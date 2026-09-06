from rest_framework import serializers

from contabilidad.servicios import balance
from contabilidad.servicios.balance import CAMPOS_FILTRABLES


class ConMovimientoInformeBalanceSerializer(serializers.Serializer):
    """
    Columnas del balance de prueba (solo lectura).

    No es un `ModelSerializer`: las filas no son movimientos ni cuentas sino lo
    que devuelve `jerarquizar`, un diccionario por auxiliar y por subtotal. La
    aritmética ya viene hecha desde el servicio, para que `lista/`, `excel/` y
    `totales/` entreguen los mismos números; acá solo se declara el contrato de
    columnas y la whitelist de filtros que consume `FiltrosDinamicosMixin`.

    `tipo` dice qué es la fila (`CLASE`, `GRUPO`, `CUENTA`, `SUBCUENTA` o
    `AUXILIAR`) y es lo único que distingue un subtotal de una cuenta: solo las
    de tipo `AUXILIAR` traen `cuenta_id`.

    No se declara `ordenamiento_default_lista`: el orden lo fija el propio
    informe (por código de cuenta) y no acepta que lo cambien.
    """

    campos_filtrables = CAMPOS_FILTRABLES

    tipo = serializers.CharField(read_only=True)
    cuenta_id = serializers.IntegerField(read_only=True, allow_null=True)
    codigo = serializers.CharField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    saldo_anterior = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_final = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeBalanceTotalesSerializer(serializers.Serializer):
    """
    Totales del balance, servidos por la acción `totales/`.

    `tipo_fila` y `columnas` le dicen a `balance.totalizar` qué sumar: los
    auxiliares y nada más, porque los subtotales y el detalle están hechos de
    ellos. Cada informe declara los suyos acá y no en la vista, que es donde ya
    vive el resto de su contrato de columnas.
    """

    tipo_fila = balance.HOJA
    columnas = balance.COLUMNAS

    saldo_anterior = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_final = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeBalanceContactoSerializer(ConMovimientoInformeBalanceSerializer):
    """
    Balance de prueba abierto por tercero.

    Es el mismo contrato con tres columnas más, vacías en todo lo que no sea una
    fila de tipo `TERCERO`: los subtotales y los auxiliares no tienen contacto,
    y el auxiliar es el total de la cuenta, no una fila más del detalle.
    """

    contacto_id = serializers.IntegerField(read_only=True, allow_null=True)
    identificacion = serializers.CharField(read_only=True, allow_null=True)
    contacto = serializers.CharField(read_only=True, allow_null=True)


class ConMovimientoInformeAuxiliarCuentaSerializer(ConMovimientoInformeBalanceSerializer):
    """
    Auxiliar por cuenta: el balance con los movimientos del rango bajo cada
    auxiliar. `movimiento_id` no tiene columna en el Excel — está para que el
    front pueda saltar del renglón al asiento.
    """

    movimiento_id = serializers.IntegerField(read_only=True, allow_null=True)


class ConMovimientoInformeAuxiliarContactoSerializer(ConMovimientoInformeBalanceContactoSerializer):
    """Auxiliar por contacto: cada tercero seguido de sus movimientos del rango."""

    movimiento_id = serializers.IntegerField(read_only=True, allow_null=True)


class ConMovimientoInformeAuxiliarGeneralSerializer(ConMovimientoInformeAuxiliarContactoSerializer):
    """
    Auxiliar general: los terceros de la cuenta y después todos sus movimientos.

    Es el único informe que identifica cada asiento — comprobante, número y
    fecha—, y por eso el único que se lee sin tener que ir al mayor.
    """

    comprobante = serializers.CharField(read_only=True, allow_null=True)
    numero = serializers.IntegerField(read_only=True, allow_null=True)
    fecha = serializers.DateField(read_only=True, allow_null=True)


class ConMovimientoInformeBasesSerializer(serializers.Serializer):
    """
    Informe de bases: un movimiento por fila, sin jerarquía.

    Lo que decide qué entra es `cuenta.exige_base`, no que el movimiento traiga
    base: un asiento a una cuenta de retención al que se le olvidó la base sale
    en cero, que es como se ve que falta.
    """

    campos_filtrables = CAMPOS_FILTRABLES

    tipo = serializers.CharField(read_only=True)
    cuenta_id = serializers.IntegerField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    contacto_id = serializers.IntegerField(read_only=True, allow_null=True)
    identificacion = serializers.CharField(read_only=True, allow_null=True)
    contacto = serializers.CharField(read_only=True, allow_null=True)
    movimiento_id = serializers.IntegerField(read_only=True)
    comprobante = serializers.CharField(read_only=True)
    numero = serializers.IntegerField(read_only=True, allow_null=True)
    fecha = serializers.DateField(read_only=True)
    detalle = serializers.CharField(read_only=True, allow_null=True)
    debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    base = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeBasesTotalesSerializer(serializers.Serializer):
    """Totales del informe de bases: todas sus filas están al mismo nivel."""

    tipo_fila = None
    columnas = ('debito', 'credito', 'base')

    debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    base = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeCertificadoSerializer(serializers.Serializer):
    """
    Certificado de retención: lo retenido a cada tercero en cada cuenta.

    `retenido` es el neto débito menos crédito y `base_retenido` el neto de las
    bases partido por el signo del movimiento, no por el de la base — la base
    siempre es positiva, lo que dice si suma o resta es si el movimiento retuvo
    o reversó.
    """

    campos_filtrables = CAMPOS_FILTRABLES

    tipo = serializers.CharField(read_only=True)
    cuenta_id = serializers.IntegerField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    contacto_id = serializers.IntegerField(read_only=True, allow_null=True)
    identificacion = serializers.CharField(read_only=True, allow_null=True)
    contacto = serializers.CharField(read_only=True, allow_null=True)
    base_retenido = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    retenido = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeCertificadoTotalesSerializer(serializers.Serializer):
    """Totales del certificado: base sujeta a retención y retenido."""

    tipo_fila = None
    columnas = ('base_retenido', 'retenido')

    base_retenido = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    retenido = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeEstadoSerializer(serializers.Serializer):
    """
    Estado de resultados y estado de situación financiera: una fila por cuenta.

    El saldo va invertido respecto del balance (`crédito − débito`), que es la
    convención con la que se leen los dos estados: ingreso positivo, gasto
    negativo.
    """

    campos_filtrables = CAMPOS_FILTRABLES

    tipo = serializers.CharField(read_only=True)
    cuenta_id = serializers.IntegerField(read_only=True)
    clase = serializers.CharField(read_only=True)
    grupo = serializers.CharField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    saldo = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeEstadoTotalesSerializer(serializers.Serializer):
    """Total de los estados: la suma de los saldos del periodo."""

    tipo_fila = None
    columnas = ('saldo',)

    saldo = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
