"""
Indicadores del tablero de contabilidad.

`estado_resultados`: el estado de resultados resumido en las pocas cifras que
lee un gerente —cuánto vendimos, cuánto gastamos, cuánto nos quedó— y en las
filas de una gráfica de cascada. Sale de `con_movimiento` en una sola consulta
agregada, sin asientos de cierre (ver `balance._SIN_CIERRE`).

Los grupos del PUC se resuelven por los FK `cuenta_grupo` y `cuenta_clase` de la
cuenta. Esos FK los llena el importador derivándolos del código, pero el CRUD
de cuentas no: una cuenta creada a mano puede tenerlos en NULL. Para que esa
cuenta no se pierda del tablero, cuando el FK falta se usa el prefijo numérico
del código, que es justo lo que el catálogo usa como id.

`pendiente_contabilizar`: cuántos documentos del periodo faltan por contabilizar,
con el mismo criterio que `contabilizar`: tipo con contabilidad, aprobado, no
anulado y el periodo sacado de `fecha_contable`.
"""
from datetime import date
from decimal import Decimal

from django.db.models import (
    Case, DecimalField, F, IntegerField, Q, Sum, Value, When,
)
from django.db.models.functions import Cast, Coalesce, Substr
from django.utils import timezone

from contabilidad.models import ConMovimiento, ConPeriodo
from general.models import GenDocumento

_CERO = Decimal('0')
_MONTO = DecimalField(max_digits=20, decimal_places=6)
_CERO_SQL = Value(_CERO, output_field=_MONTO)
_CIEN = Decimal('100')
_DOS_DECIMALES = Decimal('0.01')

GRUPO_VENTAS = 41
GRUPO_OTROS_INGRESOS = 42
GRUPOS_GASTOS_OPERACION = (51, 52)
GRUPO_OTROS_GASTOS = 53
GRUPO_IMPUESTOS = 54
CLASES_COSTO = (6, 7)


def estado_resultados(fecha_desde=None, fecha_hasta=None, hoy=None):
    """
    Cifras del estado de resultados del rango y del mismo rango un año antes.

    Sin fechas, el rango es el de `rango`.
    """
    fecha_desde, fecha_hasta = rango(fecha_desde, fecha_hasta, hoy)
    actual = _cifras(fecha_desde, fecha_hasta)
    desde_anterior, hasta_anterior = _anio_anterior(fecha_desde), _anio_anterior(fecha_hasta)
    anterior = _cifras(desde_anterior, hasta_anterior)

    return {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'tarjetas': _tarjetas(actual),
        'cascada': _cascada(actual),
        'comparativo': {
            'fecha_desde': desde_anterior,
            'fecha_hasta': hasta_anterior,
            **{
                clave: valor for clave, valor in _tarjetas(anterior).items()
                if clave != 'margen_neto'
            },
        },
    }


def rango(fecha_desde=None, fecha_hasta=None, hoy=None):
    """Completa el rango: del 1 de enero del año de `hoy` hasta `hoy`."""
    hoy = hoy or timezone.localdate()
    return fecha_desde or date(hoy.year, 1, 1), fecha_hasta or hoy


def pendiente_contabilizar(periodo_id=None, hoy=None):
    """
    Cantidad de documentos pendientes por contabilizar del periodo.

    Sin periodo, el del mes de `hoy`. El periodo es `anio*100+mes` con mes de 1 a
    12: el 13 (ajustes y cierre) no corresponde a ninguna fecha.
    """
    if periodo_id is None:
        hoy = hoy or timezone.localdate()
        periodo_id = ConPeriodo.calcular_id(hoy.year, hoy.month)
    anio, mes = divmod(periodo_id, 100)
    desde = date(anio, mes, 1)
    hasta = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)

    cantidad = GenDocumento.objects.filter(
        documento_tipo__contabilidad=True,
        estado_aprobado=True,
        estado_anulado=False,
        estado_contabilizado=False,
        fecha_contable__gte=desde,
        fecha_contable__lt=hasta,
    ).count()
    return {'periodo_id': periodo_id, 'cantidad': cantidad}


def _cifras(fecha_desde, fecha_hasta):
    """Las sumas por rubro del rango y los derivados del estado de resultados."""
    codigo_numerico = Q(cuenta__codigo__regex=r'^[0-9]{2}')
    grupo = Coalesce(
        F('cuenta__cuenta_grupo_id'),
        Case(
            When(codigo_numerico, then=Cast(Substr('cuenta__codigo', 1, 2), IntegerField())),
            default=None, output_field=IntegerField(),
        ),
    )
    clase = Coalesce(
        F('cuenta__cuenta_clase_id'),
        Case(
            When(codigo_numerico, then=Cast(Substr('cuenta__codigo', 1, 1), IntegerField())),
            default=None, output_field=IntegerField(),
        ),
    )
    credito_menos_debito = F('credito') - F('debito')
    debito_menos_credito = F('debito') - F('credito')

    def suma(expresion, filtro):
        return Coalesce(Sum(expresion, filter=filtro, output_field=_MONTO), _CERO_SQL)

    sumas = (
        ConMovimiento.objects
        .filter(fecha__gte=fecha_desde, fecha__lte=fecha_hasta, cierre=False)
        .annotate(grupo_puc=grupo, clase_puc=clase)
        .aggregate(
            ventas=suma(credito_menos_debito, Q(grupo_puc=GRUPO_VENTAS)),
            otros_ingresos=suma(credito_menos_debito, Q(grupo_puc=GRUPO_OTROS_INGRESOS)),
            costo_ventas=suma(debito_menos_credito, Q(clase_puc__in=CLASES_COSTO)),
            gastos_operacion=suma(debito_menos_credito, Q(grupo_puc__in=GRUPOS_GASTOS_OPERACION)),
            otros_gastos=suma(debito_menos_credito, Q(grupo_puc=GRUPO_OTROS_GASTOS)),
            impuestos=suma(debito_menos_credito, Q(grupo_puc=GRUPO_IMPUESTOS)),
        )
    )

    utilidad_bruta = sumas['ventas'] - sumas['costo_ventas']
    utilidad_operacional = utilidad_bruta - sumas['gastos_operacion']
    otros_netos = sumas['otros_ingresos'] - sumas['otros_gastos']
    utilidad_neta = utilidad_operacional + otros_netos - sumas['impuestos']
    margen_neto = (
        None if sumas['ventas'] == 0
        else (utilidad_neta / sumas['ventas'] * _CIEN).quantize(_DOS_DECIMALES)
    )
    return {
        **sumas,
        'utilidad_bruta': utilidad_bruta,
        'utilidad_operacional': utilidad_operacional,
        'otros_netos': otros_netos,
        'utilidad_neta': utilidad_neta,
        'margen_neto': margen_neto,
    }


def _tarjetas(cifras):
    # `vendimos − gastamos` da `nos_quedo`: lo que entra del 42 está en vendimos y
    # lo que sale del 53 en gastamos, en vez de netearlos como en la cascada.
    return {
        'vendimos': cifras['ventas'] + cifras['otros_ingresos'],
        'gastamos': (
            cifras['costo_ventas'] + cifras['gastos_operacion']
            + cifras['otros_gastos'] + cifras['impuestos']
        ),
        'nos_quedo': cifras['utilidad_neta'],
        'margen_neto': cifras['margen_neto'],
    }


def _cascada(cifras):
    """Filas de la cascada: las de `entrada`/`salida` suman `utilidad_neta`."""
    otros = cifras['otros_netos']
    return [
        _fila('ventas', 'Ventas', cifras['ventas'], 'entrada'),
        _fila('costo_ventas', 'Costo de lo vendido', _CERO - cifras['costo_ventas'], 'salida'),
        _fila('utilidad_bruta', 'Queda (bruta)', cifras['utilidad_bruta'], 'subtotal'),
        _fila('gastos_operacion', 'Gastos de operación', _CERO - cifras['gastos_operacion'], 'salida'),
        _fila('utilidad_operacional', 'Queda (operación)', cifras['utilidad_operacional'], 'subtotal'),
        _fila('otros_netos', 'Otros ingresos y gastos', otros, 'salida' if otros < 0 else 'entrada'),
        _fila('impuestos', 'Impuestos', _CERO - cifras['impuestos'], 'salida'),
        _fila('utilidad_neta', 'Ganancia', cifras['utilidad_neta'], 'total'),
    ]


def _fila(clave, etiqueta, valor, tipo):
    return {'clave': clave, 'etiqueta': etiqueta, 'valor': valor, 'tipo': tipo}


def _anio_anterior(fecha):
    """La misma fecha un año antes; el 29 de febrero cae en el 28."""
    try:
        return fecha.replace(year=fecha.year - 1)
    except ValueError:
        return fecha.replace(year=fecha.year - 1, day=28)
