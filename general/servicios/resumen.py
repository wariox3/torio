"""
Resumen de ventas o compras para el tablero: el neto del periodo en curso, por día o
por mes.

Entran los documentos con `documento_tipo.venta` (o `compra`) aprobados y no
anulados, por su `fecha`. Cada valor se multiplica por `documento_tipo.operacion`,
así las notas crédito y de ajuste (-1) restan y el resultado es el neto. Los tipos
de operación cero (pedidos, remisiones) no entran: no son la venta ni la compra, y
aunque no sumarían en los valores sí inflarían el conteo de `documentos`.

- `mes`: del primer al último día del mes de `hoy`, un punto por día.
- `anio`: de enero a diciembre del año de `hoy`, un punto por mes.

Los días o meses sin ventas también salen, en cero, para que la serie llegue completa.
"""
import calendar
from datetime import date
from decimal import Decimal

from django.db.models import Case, Count, F, Sum, When
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone

from general.models import GenDocumento

# Lado del resumen → indicador de `GenDocumentoTipo` que lo marca.
TIPOS = {
    'venta': 'documento_tipo__venta',
    'compra': 'documento_tipo__compra',
}

PERIODOS = ('mes', 'anio')

CAMPOS = ('subtotal', 'impuesto', 'total')

# Nómina, primas, cesantías, intereses y liquidaciones (701) y seguridad social (703).
DOCUMENTO_CLASE_NOMINA = 701
DOCUMENTO_CLASE_SEGURIDAD_SOCIAL = 703


def _rango(periodo, hoy):
    if periodo == 'mes':
        ultimo = calendar.monthrange(hoy.year, hoy.month)[1]
        return date(hoy.year, hoy.month, 1), date(hoy.year, hoy.month, ultimo)
    return date(hoy.year, 1, 1), date(hoy.year, 12, 31)


def _puntos(periodo, desde, hasta):
    if periodo == 'mes':
        return [date(desde.year, desde.month, dia) for dia in range(1, hasta.day + 1)]
    return [date(desde.year, mes, 1) for mes in range(1, 13)]


def resumen(tipo, periodo, hoy=None):
    hoy = hoy or timezone.localdate()
    desde, hasta = _rango(periodo, hoy)
    truncar = TruncDay if periodo == 'mes' else TruncMonth

    # El `order_by()` vacío evita que el `-id` del modelo entre al GROUP BY.
    filas = (
        GenDocumento.objects
        .filter(
            **{TIPOS[tipo]: True},
            estado_aprobado=True,
            estado_anulado=False,
            fecha__range=(desde, hasta),
        )
        .exclude(documento_tipo__operacion=0)
        .annotate(punto=truncar('fecha'))
        .order_by()
        .values('punto')
        .annotate(
            documentos=Count('id'),
            **{
                campo: Sum(F(campo) * F('documento_tipo__operacion'))
                for campo in CAMPOS
            },
        )
    )
    cero = Decimal('0')
    por_punto = {fila['punto']: fila for fila in filas}

    serie = []
    totales = {'documentos': 0, **{campo: cero for campo in CAMPOS}}
    for punto in _puntos(periodo, desde, hasta):
        fila = por_punto.get(punto, {})
        item = {
            'fecha': punto.isoformat() if periodo == 'mes' else punto.strftime('%Y-%m'),
            'documentos': fila.get('documentos', 0),
            **{campo: fila.get(campo) or cero for campo in CAMPOS},
        }
        for campo in ('documentos', *CAMPOS):
            totales[campo] += item[campo]
        serie.append(item)

    return {
        'periodo': periodo,
        'fecha_desde': desde,
        'fecha_hasta': hasta,
        'serie': serie,
        'totales': totales,
    }


def _personal(periodo, hoy):
    """
    Gasto de personal por punto: el `devengado` de la nómina (clase 701) y el
    `subtotal` de la seguridad social (clase 703).

    Va el devengado y no el `total`: lo deducido (salud y pensión del empleado,
    créditos) también lo paga la empresa, solo que a otro. De la seguridad social
    va el `subtotal`, la parte de la empresa; la del empleado ya está en el devengado.
    """
    desde, hasta = _rango(periodo, hoy)
    truncar = TruncDay if periodo == 'mes' else TruncMonth
    filas = (
        GenDocumento.objects
        .filter(
            documento_tipo__documento_clase_id__in=(DOCUMENTO_CLASE_NOMINA, DOCUMENTO_CLASE_SEGURIDAD_SOCIAL),
            estado_aprobado=True,
            estado_anulado=False,
            fecha__range=(desde, hasta),
        )
        .annotate(punto=truncar('fecha'))
        .order_by()
        .values('punto')
        .annotate(valor=Sum(Case(
            When(documento_tipo__documento_clase_id=DOCUMENTO_CLASE_NOMINA, then=F('devengado')),
            default=F('subtotal'),
        )))
    )
    return {fila['punto']: fila['valor'] or Decimal('0') for fila in filas}


def resultado(periodo, hoy=None):
    """
    Ingresos contra costos y gastos, para el gráfico de dos barras en cada punto:
    `ingreso` es el `subtotal` neto de las ventas y `egreso` el de las compras más
    el gasto de personal (nómina, primas, cesantías, intereses, liquidaciones y
    seguridad social, ver `_personal`).

    Va antes de impuestos porque el IVA no es ingreso ni gasto: con el `total`
    las dos barras quedarían infladas.
    """
    hoy = hoy or timezone.localdate()
    ventas = resumen('venta', periodo, hoy)
    compras = resumen('compra', periodo, hoy)
    personal = _personal(periodo, hoy)
    puntos = _puntos(periodo, ventas['fecha_desde'], ventas['fecha_hasta'])
    cero = Decimal('0')
    serie = [
        {
            'fecha': venta['fecha'],
            'ingreso': venta['subtotal'],
            'egreso': compra['subtotal'] + personal.get(punto, cero),
        }
        for punto, venta, compra in zip(puntos, ventas['serie'], compras['serie'])
    ]
    ingreso = ventas['totales']['subtotal']
    egreso = sum((item['egreso'] for item in serie), cero)
    return {
        'periodo': periodo,
        'fecha_desde': ventas['fecha_desde'],
        'fecha_hasta': ventas['fecha_hasta'],
        'serie': serie,
        'totales': {'ingreso': ingreso, 'egreso': egreso, 'diferencia': ingreso - egreso},
    }
