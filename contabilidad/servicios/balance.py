"""
Balance de prueba: consolidado por cuenta de un rango de fechas.
"""
from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from contabilidad.models import ConMovimiento

# Whitelist de filtros dinámicos del informe. `fecha` no está a propósito: el
# rango del balance la gobierna, y un filtro por fecha encima del rango daría
# dos cortes distintos para el saldo anterior y para el movimiento.
CAMPOS_FILTRABLES = {
    'cuenta_id',
    'cuenta__codigo',
    'cuenta__nombre',
    'centro_costo_id',
    'contacto_id',
    'comprobante_id',
    'documento_id',
    'periodo_id',
    'numero',
    'naturaleza',
    'cierre',
    'saldo_inicial',
}

_CERO = Decimal('0')
_CERO_SQL = Value(_CERO, output_field=DecimalField(max_digits=20, decimal_places=6))

# Columnas que suma `totalizar` y que tienen que cuadrar entre sí.
COLUMNAS_TOTALIZABLES = (
    'saldo_anterior_debito',
    'saldo_anterior_credito',
    'debito',
    'credito',
    'saldo_final_debito',
    'saldo_final_credito',
)


def balance_prueba(fecha_desde, fecha_hasta):
    """
    Queryset agrupado por cuenta con el movimiento del rango y el acumulado previo.

    Un solo barrido de `con_movimiento` resuelve las dos mitades: los `Sum` con
    `filter` separan lo anterior a `fecha_desde` de lo que cae dentro del rango,
    y el `filter(fecha__lte=fecha_hasta)` de entrada acota el scan por arriba.
    Las cuentas sin movimiento en el rango pero con saldo anterior aparecen
    igual; las que nunca tuvieron un movimiento no aparecen nunca.

    El saldo anterior suma desde el primer movimiento de la historia, porque no
    hay saldo guardado en ninguna parte: `con_saldo_cuenta` existe como modelo
    pero nadie la escribe todavía. Cuando se consolide al bloquear el periodo,
    esta función es el único lugar que cambia — el informe, la API y el front no
    se enteran.

    Devuelve los importes crudos (`anterior_debito`, `anterior_credito`,
    `movimiento_debito`, `movimiento_credito`); las columnas que ve el usuario
    las arma `componer_fila`.

    El `order_by` explícito no es cosmético: `ConMovimiento.Meta.ordering` es
    `['-id']`, y sobre un queryset agrupado Django mete el campo de ordenamiento
    en el GROUP BY, con lo que el balance saldría partido en una fila por
    movimiento en vez de una por cuenta.
    """
    return (
        ConMovimiento.objects.filter(fecha__lte=fecha_hasta)
        .values('cuenta_id', 'cuenta__codigo', 'cuenta__nombre')
        .annotate(
            anterior_debito=Coalesce(Sum('debito', filter=Q(fecha__lt=fecha_desde)), _CERO_SQL),
            anterior_credito=Coalesce(Sum('credito', filter=Q(fecha__lt=fecha_desde)), _CERO_SQL),
            movimiento_debito=Coalesce(Sum('debito', filter=Q(fecha__gte=fecha_desde)), _CERO_SQL),
            movimiento_credito=Coalesce(Sum('credito', filter=Q(fecha__gte=fecha_desde)), _CERO_SQL),
        )
        .order_by('cuenta__codigo')
    )


def componer_fila(fila):
    """
    Traduce los importes crudos de una fila agrupada a las columnas del balance.

    El saldo se netea por cuenta (`débito - crédito`) y se presenta en una sola
    de las dos columnas, como manda la forma clásica del balance de prueba; la
    otra queda en cero. Se entrega además el neto con signo, que es lo que sirve
    para sumar sin volver a interpretar las columnas.
    """
    saldo_anterior = fila['anterior_debito'] - fila['anterior_credito']
    debito = fila['movimiento_debito']
    credito = fila['movimiento_credito']
    saldo_final = saldo_anterior + debito - credito

    anterior_debito, anterior_credito = _partir(saldo_anterior)
    final_debito, final_credito = _partir(saldo_final)

    return {
        'cuenta_id': fila['cuenta_id'],
        'cuenta_codigo': fila['cuenta__codigo'],
        'cuenta_nombre': fila['cuenta__nombre'],
        'saldo_anterior_debito': anterior_debito,
        'saldo_anterior_credito': anterior_credito,
        'saldo_anterior': saldo_anterior,
        'debito': debito,
        'credito': credito,
        'saldo_final_debito': final_debito,
        'saldo_final_credito': final_credito,
        'saldo_final': saldo_final,
    }


def totalizar(filas):
    """
    Suma las columnas ya compuestas, no los importes crudos.

    Es lo que hace que el total de débito iguale al de crédito: el cuadre del
    balance sale del neteo por cuenta, así que sumar los crudos daría otra cosa
    y el total no coincidiría con lo que el usuario ve en pantalla.
    """
    totales = {columna: _CERO for columna in COLUMNAS_TOTALIZABLES}
    for fila in filas:
        compuesta = componer_fila(fila)
        for columna in COLUMNAS_TOTALIZABLES:
            totales[columna] += compuesta[columna]
    return totales


def _partir(saldo):
    """Un saldo neto va en la columna de débito si es positivo y en la de crédito si no."""
    if saldo >= _CERO:
        return saldo, _CERO
    return _CERO, -saldo
