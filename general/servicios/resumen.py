"""
Resumen de ventas para el tablero: la venta neta del periodo en curso, por día o por mes.

Entran los documentos con `documento_tipo.venta` aprobados y no anulados, por su
`fecha`. Cada valor se multiplica por `documento_tipo.operacion`, así la nota
crédito (-1) resta de lo facturado y el resultado es la venta neta.

- `mes`: del primer al último día del mes de `hoy`, un punto por día.
- `anio`: de enero a diciembre del año de `hoy`, un punto por mes.

Los días o meses sin ventas también salen, en cero, para que la serie llegue completa.
"""
import calendar
from datetime import date
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone

from general.models import GenDocumento

PERIODOS = ('mes', 'anio')

CAMPOS = ('subtotal', 'impuesto', 'total')


def _rango(periodo, hoy):
    if periodo == 'mes':
        ultimo = calendar.monthrange(hoy.year, hoy.month)[1]
        return date(hoy.year, hoy.month, 1), date(hoy.year, hoy.month, ultimo)
    return date(hoy.year, 1, 1), date(hoy.year, 12, 31)


def _puntos(periodo, desde, hasta):
    if periodo == 'mes':
        return [date(desde.year, desde.month, dia) for dia in range(1, hasta.day + 1)]
    return [date(desde.year, mes, 1) for mes in range(1, 13)]


def resumen(periodo, hoy=None):
    hoy = hoy or timezone.localdate()
    desde, hasta = _rango(periodo, hoy)
    truncar = TruncDay if periodo == 'mes' else TruncMonth

    # El `order_by()` vacío evita que el `-id` del modelo entre al GROUP BY.
    filas = (
        GenDocumento.objects
        .filter(
            documento_tipo__venta=True,
            estado_aprobado=True,
            estado_anulado=False,
            fecha__range=(desde, hasta),
        )
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
