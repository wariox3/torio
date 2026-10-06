"""
Redondeo del dinero.

Las columnas de valor guardan 6 decimales, pero el dinero se maneja en centavos:
nadie paga 14161.2142, y un residuo así deja la factura con saldo pendiente para
siempre y el asiento descuadrado por fracciones. Por eso todo valor en dinero que
se calcula o se digita pasa por acá antes de guardarse. El precio unitario, la
cantidad y el costo promedio no: esos sí necesitan los 6 decimales.

La mitad va hacia arriba (0.125 → 0.13), que es lo que se espera comercialmente.
`quantize` sin `rounding` usa el redondeo bancario (0.125 → 0.12).
"""
from decimal import ROUND_HALF_UP, Decimal

CENTAVOS = Decimal('0.01')


def redondear_moneda(valor):
    """A centavos, con la mitad hacia arriba."""
    return Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
