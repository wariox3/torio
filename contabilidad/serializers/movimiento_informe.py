from rest_framework import serializers

from contabilidad.models import ConMovimiento
from contabilidad.servicios.balance import CAMPOS_FILTRABLES, componer_fila


class ConMovimientoInformeBalanceSerializer(serializers.Serializer):
    """
    Columnas del balance de prueba (plano, solo lectura).

    No es un `ModelSerializer`: las filas no son movimientos sino los grupos que
    devuelve `balance_prueba`, un diccionario por cuenta. La aritmética vive en
    `componer_fila` para que `lista/`, `excel/` y `totales/` entreguen los mismos
    números; acá solo se declara el contrato de columnas y la whitelist de
    filtros que consume `FiltrosDinamicosMixin`.

    No se declara `ordenamiento_default_lista`: el orden lo fija el propio
    queryset agrupado (por código de cuenta) y el informe no acepta que lo
    cambien.
    """

    campos_filtrables = CAMPOS_FILTRABLES

    cuenta_id = serializers.IntegerField(read_only=True)
    cuenta_codigo = serializers.CharField(read_only=True)
    cuenta_nombre = serializers.CharField(read_only=True)
    saldo_anterior_debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_anterior_credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_anterior = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_final_debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_final_credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_final = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)

    def to_representation(self, fila):
        return super().to_representation(componer_fila(fila))


class ConMovimientoInformeBalanceTotalesSerializer(serializers.Serializer):
    """Totales de cuadre del balance, servidos por la acción `totales/`."""

    saldo_anterior_debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_anterior_credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_final_debito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)
    saldo_final_credito = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True)


class ConMovimientoInformeBalanceExportarSerializer(serializers.Serializer):
    """Estructura del Excel del balance de prueba (usada por `ExportarExcelMixin`)."""

    model = ConMovimiento
    nombre_archivo = 'balance_prueba'
    hoja = 'Balance de prueba'

    campos_excel = (
        ('cuenta_codigo', 'Código'),
        ('cuenta_nombre', 'Cuenta'),
        ('saldo_anterior_debito', 'Saldo anterior débito'),
        ('saldo_anterior_credito', 'Saldo anterior crédito'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('saldo_final_debito', 'Saldo final débito'),
        ('saldo_final_credito', 'Saldo final crédito'),
    )

    @staticmethod
    def valor_excel(fila, campo):
        # El mixin pide celda por celda; componer la fila entera nueve veces es
        # aritmética sobre cuatro decimales y el informe tiene tantas filas como
        # cuentas con movimiento, no como movimientos.
        return componer_fila(fila)[campo]
