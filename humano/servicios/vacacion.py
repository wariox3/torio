"""
Periodos de vacaciones de un contrato.

Por cada 360 días trabajados (30/360) se causan 15 días hábiles de vacaciones, así
que cada día de vacaciones —disfrutado o pagado en dinero— cubre 24 días del
periodo. Tomar 7 de los 15 cierra solo 168 días del año y deja los otros 8
pendientes en el periodo siguiente.

Hasta dónde están cubiertas las vacaciones no se guarda, se calcula: desde
`HumContrato.fecha_ultimo_pago_vacacion` —el corte con el que se creó el
contrato— se avanzan 24 días por cada día tomado en sus novedades de vacaciones
(`dias_disfrutados`, hábiles, más `dias_dinero`). Calculado, editar o borrar una
novedad no deja el contrato desfasado.

Se suman los días y no se toma el `fecha_hasta_periodo` de las novedades porque
ese campo lo escribe el usuario: una novedad con el periodo mal puesto (las
fechas del disfrute, por ejemplo) haría saltar el corte y se perderían días.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import F, Sum
from django.utils import timezone

from humano.models import HumNovedad
from humano.servicios.nomina import NOVEDAD_TIPO_VACACION
from utilidades.fechas import dias_prestacionales, sumar_dias_prestacionales

DIAS_VACACION_ANIO = Decimal('15')
DIAS_ANIO = Decimal('360')
DIAS_PERIODO_POR_DIA = DIAS_ANIO / DIAS_VACACION_ANIO  # 24


def corte_inicial(contrato):
    """Sin vacaciones previas, el primer periodo arranca con el contrato."""
    return contrato.fecha_ultimo_pago_vacacion or contrato.fecha_desde - timedelta(days=1)


def _dias_periodo(dias):
    """Días del periodo (30/360) que cubren `dias` días de vacaciones."""
    return int((Decimal(dias) * DIAS_PERIODO_POR_DIA).to_integral_value(ROUND_HALF_UP))


def ultimo_periodo_vacacion(contrato):
    """El último día cubierto por vacaciones (disfrutadas o pagadas en dinero)."""
    tomados = (
        HumNovedad.objects
        .filter(contrato=contrato, novedad_tipo_id=NOVEDAD_TIPO_VACACION)
        .aggregate(dias=Sum(F('dias_disfrutados') + F('dias_dinero')))['dias']
    )
    inicial = corte_inicial(contrato)
    dias_periodo = _dias_periodo(tomados or 0)
    if dias_periodo < 1:
        return inicial
    return sumar_dias_prestacionales(inicial + timedelta(days=1), dias_periodo)


def periodo_sugerido(contrato, dias=DIAS_VACACION_ANIO, hoy=None):
    """
    El periodo que cubrirían `dias` días de vacaciones a partir del último
    cubierto, y los días causados y aún no tomados a `hoy` (o al fin del contrato
    si terminó antes).
    """
    hoy = hoy or timezone.localdate()
    desde = ultimo_periodo_vacacion(contrato) + timedelta(days=1)
    hasta = sumar_dias_prestacionales(desde, max(_dias_periodo(dias), 1))

    corte = min(hoy, contrato.fecha_hasta) if contrato.estado_terminado else hoy
    trabajados = dias_prestacionales(desde, corte) if corte >= desde else 0
    causados = (Decimal(trabajados) * DIAS_VACACION_ANIO / DIAS_ANIO).quantize(Decimal('0.001'), ROUND_HALF_UP)
    return {
        'fecha_desde_periodo': desde,
        'fecha_hasta_periodo': hasta,
        'dias_causados': causados,
    }
