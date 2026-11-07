"""
Estado de resultados formal: el que se presenta, con secciones, subtotales y
utilidades, y la columna del mismo rango un año antes para comparar.

Convive con el informe `estado_resultados` del registro, que es una fila por
auxiliar sin estructura: ese es la materia prima, este la presentación.

Las secciones son los mismos rubros del tablero (`tablero._cifras`), así que la
utilidad neta de los dos coincide: ingresos operacionales (41), costo de ventas
(clases 6 y 7), gastos de administración (51) y de ventas (52), no operacionales
(42 y 53) e impuesto de renta (54). Lo que no esté en ninguna sección —47 o 59,
que en la práctica no se mueven fuera del cierre— tampoco entra al tablero.

El detalle va a nivel de cuenta (4 dígitos). Igual que el tablero, cuando a la
cuenta auxiliar le faltan los FK de clase, grupo o cuenta se sacan del prefijo
del código, que es lo que el catálogo usa como id: una cuenta creada a mano no
se pierde del informe.

Cada sección se presenta en positivo en su naturaleza (el ingreso crédito −
débito, el costo y el gasto débito − crédito) y las restas se hacen en las
utilidades, que es como se lee un estado formal. Una devolución en ventas, que
es un débito del 41, resta dentro de los ingresos.
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from contabilidad.models import ConCuentaCuenta, ConMovimiento
from contabilidad.servicios.tablero import (
    CLASES_COSTO,
    GRUPO_IMPUESTOS,
    GRUPO_OTROS_GASTOS,
    GRUPO_OTROS_INGRESOS,
    GRUPO_VENTAS,
)

_CERO = Decimal('0')
_CERO_SQL = Value(_CERO, output_field=DecimalField(max_digits=20, decimal_places=6))

GRUPO_GASTOS_ADMINISTRACION = 51
GRUPO_GASTOS_VENTAS = 52
CLASES_RESULTADO = (4, 5, 6, 7)

# Tipos de fila, de arriba abajo dentro de una sección.
SECCION = 'SECCION'
CUENTA = 'CUENTA'
TOTAL = 'TOTAL'
UTILIDAD = 'UTILIDAD'

# Naturaleza con la que se presenta cada sección y su efecto en la utilidad.
_INGRESO = ('C', 1)
_GASTO = ('D', -1)

# El estado en orden. Una sección suma (o resta) a la utilidad que se arrastra;
# una utilidad muestra lo acumulado hasta ahí.
ESTRUCTURA = (
    (SECCION, 'Ingresos operacionales', _INGRESO, {'grupos': (GRUPO_VENTAS,)}),
    (SECCION, 'Costo de ventas', _GASTO, {'clases': CLASES_COSTO}),
    (UTILIDAD, 'Utilidad bruta'),
    (SECCION, 'Gastos operacionales de administración', _GASTO, {'grupos': (GRUPO_GASTOS_ADMINISTRACION,)}),
    (SECCION, 'Gastos operacionales de ventas', _GASTO, {'grupos': (GRUPO_GASTOS_VENTAS,)}),
    (UTILIDAD, 'Utilidad operacional'),
    (SECCION, 'Ingresos no operacionales', _INGRESO, {'grupos': (GRUPO_OTROS_INGRESOS,)}),
    (SECCION, 'Gastos no operacionales', _GASTO, {'grupos': (GRUPO_OTROS_GASTOS,)}),
    (UTILIDAD, 'Utilidad antes de impuestos'),
    (SECCION, 'Impuesto de renta y complementarios', _GASTO, {'grupos': (GRUPO_IMPUESTOS,)}),
    (UTILIDAD, 'Utilidad neta del periodo'),
)


def agrupar(fecha_desde, fecha_hasta):
    """
    Débitos y créditos del rango por cuenta auxiliar de resultado, sin cierre.

    Es el `agrupar` del registro de informes: los filtros dinámicos se aplican
    sobre este queryset, antes de que se agrupe.
    """
    return (
        ConMovimiento.objects
        .filter(fecha__gte=fecha_desde, fecha__lte=fecha_hasta, cierre=False)
        .filter(
            Q(cuenta__cuenta_clase_id__in=CLASES_RESULTADO)
            | Q(cuenta__cuenta_clase__isnull=True, cuenta__codigo__regex=r'^[4-7]')
        )
        .values(
            'cuenta__codigo', 'cuenta__cuenta_clase_id',
            'cuenta__cuenta_grupo_id', 'cuenta__cuenta_cuenta_id',
        )
        .annotate(
            total_debito=Coalesce(Sum('debito'), _CERO_SQL),
            total_credito=Coalesce(Sum('credito'), _CERO_SQL),
        )
        .order_by('cuenta__codigo')
    )


def filas(actual, anterior):
    """
    Las filas del estado: por cada sección su título, sus cuentas y su total,
    y entre secciones las utilidades. Cada fila trae `actual`, `anterior`,
    `variacion` y `porcentaje` (fracción: 0.25 es 25 %); el título no trae
    importes.
    """
    saldos = {'actual': _por_seccion(actual), 'anterior': _por_seccion(anterior)}
    codigos = {
        codigo
        for periodo in saldos.values() for cuentas in periodo.values() for codigo in cuentas
    }
    nombres = dict(
        ConCuentaCuenta.objects.filter(id__in=[int(c) for c in codigos if c.isdigit()])
        .values_list('id', 'nombre')
    )

    resultado = []
    utilidad = {'actual': _CERO, 'anterior': _CERO}
    for indice, (tipo, titulo, *resto) in enumerate(ESTRUCTURA):
        if tipo == UTILIDAD:
            resultado.append(_fila(UTILIDAD, '', titulo, utilidad['actual'], utilidad['anterior']))
            continue

        (_, signo), _ = resto
        actual_seccion = saldos['actual'].get(indice, {})
        anterior_seccion = saldos['anterior'].get(indice, {})
        resultado.append({'tipo': SECCION, 'codigo': '', 'nombre': titulo,
                          'actual': None, 'anterior': None, 'variacion': None, 'porcentaje': None})
        for codigo in sorted(set(actual_seccion) | set(anterior_seccion)):
            valor_actual = actual_seccion.get(codigo, _CERO)
            valor_anterior = anterior_seccion.get(codigo, _CERO)
            if valor_actual == 0 and valor_anterior == 0:
                continue
            nombre = nombres.get(int(codigo)) if codigo.isdigit() else None
            resultado.append(_fila(CUENTA, codigo, nombre or f'Cuenta {codigo}', valor_actual, valor_anterior))

        total_actual = sum(actual_seccion.values(), _CERO)
        total_anterior = sum(anterior_seccion.values(), _CERO)
        resultado.append(_fila(TOTAL, '', f'Total {titulo[0].lower()}{titulo[1:]}', total_actual, total_anterior))
        utilidad['actual'] += signo * total_actual
        utilidad['anterior'] += signo * total_anterior
    return resultado


def _por_seccion(agrupado):
    """`{indice de la sección en ESTRUCTURA: {cuenta de 4 dígitos: valor}}`."""
    secciones = defaultdict(lambda: defaultdict(lambda: _CERO))
    for fila in agrupado:
        codigo = fila['cuenta__codigo'] or ''
        clase = fila['cuenta__cuenta_clase_id'] or _prefijo(codigo, 1)
        grupo = fila['cuenta__cuenta_grupo_id'] or _prefijo(codigo, 2)
        cuenta = fila['cuenta__cuenta_cuenta_id'] or _prefijo(codigo, 4)
        indice = _seccion(clase, grupo)
        if indice is None:
            continue
        (naturaleza, _), _ = ESTRUCTURA[indice][2:]
        neto = fila['total_credito'] - fila['total_debito']
        secciones[indice][str(cuenta) if cuenta else codigo] += neto if naturaleza == 'C' else -neto
    return secciones


def _seccion(clase, grupo):
    for indice, (tipo, *resto) in enumerate(ESTRUCTURA):
        if tipo != SECCION:
            continue
        criterio = resto[2]
        if grupo in criterio.get('grupos', ()) or clase in criterio.get('clases', ()):
            return indice
    return None


def _prefijo(codigo, largo):
    prefijo = codigo[:largo]
    return int(prefijo) if len(prefijo) == largo and prefijo.isdigit() else None


def _fila(tipo, codigo, nombre, actual, anterior):
    variacion = actual - anterior
    return {
        'tipo': tipo,
        'codigo': codigo,
        'nombre': nombre,
        'actual': actual,
        'anterior': anterior,
        'variacion': variacion,
        # Sobre el valor absoluto: una pérdida que se reduce es una mejora y
        # tiene que verse positiva.
        'porcentaje': None if anterior == 0 else variacion / abs(anterior),
    }
