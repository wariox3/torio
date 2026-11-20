"""
Periodos de vacaciones de un contrato.

Por cada 360 días trabajados (30/360) se causan 15 días hábiles de vacaciones, así
que cada día de vacaciones —disfrutado o pagado en dinero— cubre 24 días del
periodo. Tomar 7 de los 15 cierra solo 168 días del año y deja los otros 8
pendientes en el periodo siguiente.

`HumContrato.fecha_ultimo_pago_vacacion` es hasta dónde están cubiertas las
vacaciones **aprobadas**: al crear el contrato es el corte con que entra (el día
anterior al inicio, o hasta donde las tomó en otro sistema) y solo lo mueve
`aprobar_vacacion`. Es la fecha que usa la liquidación, como la de prima y
cesantía.

El periodo de cada novedad (`fecha_desde_periodo`, `fecha_hasta_periodo`) no lo
escribe el usuario. Las aprobadas lo tienen fijo; las pendientes se encadenan
desde la fecha del contrato con `recalcular_periodos`, que corre cada vez que se
crea, edita o borra una, porque cambiar los días de una corre las siguientes.
Por eso se aprueban en orden: solo la primera pendiente.

Una incapacidad durante las vacaciones las interrumpe (CST art. 188):
`interrumpir_vacacion` deja la novedad con lo que alcanzó a disfrutar, aunque
esté aprobada, y
los hábiles que faltaron se registran después como una vacación nueva
(la reanudación), que se encadena como cualquier pendiente.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q

from general.models import GenDocumentoDetalle
from humano.models import HumContrato, HumNovedad
from humano.servicios import novedad as servicio_novedad
from humano.servicios.nomina import NOVEDAD_TIPO_VACACION
from utilidades.fechas import sumar_dias_prestacionales

DIAS_VACACION_ANIO = Decimal('15')
DIAS_ANIO = Decimal('360')
DIAS_PERIODO_POR_DIA = DIAS_ANIO / DIAS_VACACION_ANIO  # 24


class VacacionError(ValueError):
    """Un motivo por el que la vacación no se puede aprobar o interrumpir; va como `detail`."""

    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


def corte_inicial(contrato):
    """
    El último día cubierto por vacaciones aprobadas. Sin ninguna, el día anterior
    al inicio: el primer periodo arranca con el contrato.
    """
    return contrato.fecha_ultimo_pago_vacacion or contrato.fecha_desde - timedelta(days=1)


def _dias_periodo(dias):
    """Días del periodo (30/360) que cubren `dias` días de vacaciones."""
    return int((Decimal(dias) * DIAS_PERIODO_POR_DIA).to_integral_value(ROUND_HALF_UP))


def recalcular_periodos(contrato_ids):
    """
    Encadena el periodo de las vacaciones pendientes (sin aprobar) de los
    contratos, en orden de disfrute, a partir del último día aprobado: cada una
    arranca el día siguiente al fin de la anterior y cubre 24 días por día tomado
    (`dias_disfrutados` + `dias_dinero`). Las aprobadas no se tocan.

    Se redondea sobre el acumulado y no por novedad, para que partir una vacación
    en dos no cambie dónde termina. Una novedad que no alcanza a cubrir un día
    queda sin periodo.
    """
    contrato_ids = {pk for pk in contrato_ids if pk is not None}
    if not contrato_ids:
        return
    with transaction.atomic():
        # Bloquea los contratos: dos vacaciones del mismo contrato guardadas a la
        # vez recalcularían cada una sin ver la otra.
        contratos = HumContrato.objects.select_for_update().filter(pk__in=contrato_ids).order_by('pk')
        cambiadas = []
        for contrato in contratos:
            novedades = HumNovedad.objects.filter(
                contrato=contrato, novedad_tipo_id=NOVEDAD_TIPO_VACACION, estado_aprobado=False,
            ).order_by('fecha_desde', 'id')
            inicio = corte_inicial(contrato) + timedelta(days=1)
            acumulado = Decimal('0')
            cubierto = 0
            for novedad in novedades:
                acumulado += novedad.dias_disfrutados + novedad.dias_dinero
                total = _dias_periodo(acumulado)
                if total > cubierto:
                    desde = sumar_dias_prestacionales(inicio, cubierto) + timedelta(days=1) if cubierto else inicio
                    hasta = sumar_dias_prestacionales(inicio, total)
                    cubierto = total
                else:
                    desde = hasta = None
                if (novedad.fecha_desde_periodo, novedad.fecha_hasta_periodo) != (desde, hasta):
                    novedad.fecha_desde_periodo, novedad.fecha_hasta_periodo = desde, hasta
                    cambiadas.append(novedad)
        if cambiadas:
            HumNovedad.objects.bulk_update(cambiadas, ['fecha_desde_periodo', 'fecha_hasta_periodo'])


def aprobar_vacacion(novedad):
    """
    Aprueba una vacación y lleva `fecha_ultimo_pago_vacacion` del contrato al fin
    de su periodo. Solo la primera pendiente del contrato: si se aprobara una
    posterior, el contrato saltaría por encima de los días de la anterior.
    """
    with transaction.atomic():
        contrato = HumContrato.objects.select_for_update().get(pk=novedad.contrato_id)
        novedad = HumNovedad.objects.select_for_update().get(pk=novedad.pk)
        if novedad.novedad_tipo_id != NOVEDAD_TIPO_VACACION:
            raise VacacionError('La novedad no es de vacaciones.')
        if novedad.estado_aprobado:
            raise VacacionError('La vacación ya está aprobada.')

        # Con el contrato bloqueado, el periodo se recalcula por si quedó viejo.
        recalcular_periodos({contrato.pk})
        novedad.refresh_from_db()
        primera = (
            HumNovedad.objects
            .filter(contrato=contrato, novedad_tipo_id=NOVEDAD_TIPO_VACACION, estado_aprobado=False)
            .order_by('fecha_desde', 'id').first()
        )
        if primera.pk != novedad.pk:
            raise VacacionError(
                f'Primero debe aprobarse la vacación {primera.pk} del {primera.fecha_desde}: '
                'se aprueban en orden.'
            )
        if novedad.fecha_hasta_periodo is None:
            raise VacacionError('La vacación no tiene días disfrutados ni en dinero: no cubre ningún periodo.')

        novedad.estado_aprobado = True
        novedad.save(update_fields=['estado_aprobado'])
        contrato.fecha_ultimo_pago_vacacion = novedad.fecha_hasta_periodo
        contrato.save(update_fields=['fecha_ultimo_pago_vacacion'])
    return novedad


def interrumpir_vacacion(novedad, fecha_desde, fecha_hasta, dias_disfrutados, dias_disfrutados_reales):
    """
    Deja la vacación con las fechas y los días que realmente disfrutó antes de la
    incapacidad que la interrumpió. Los valores llegan finales: no se calcula nada
    en proporción. Los hábiles que deja de tomar se devuelven para registrarlos
    en la reanudación.

    Una vacación con días en dinero no se interrumpe: la nómina paga el dinero
    por día disfrutado (`pago_dinero` / días reales), y cambiar los días
    descuadraría lo ya pagado contra la novedad.

    El rango nuevo tiene que caber en el original: la vacación solo libera días,
    así no puede quedar cruzada con otra novedad del empleado.

    Una aprobada también se puede interrumpir, si es la última aprobada del
    contrato: su periodo se acorta y `fecha_ultimo_pago_vacacion` retrocede con él.

    Devuelve `(novedad, dias_disfrutados_pendientes)`.
    """
    with transaction.atomic():
        contrato = HumContrato.objects.select_for_update().get(pk=novedad.contrato_id)
        novedad = HumNovedad.objects.select_for_update().select_related(
            'contrato', 'novedad_tipo__concepto', 'novedad_tipo__concepto2', 'novedad_referencia',
        ).get(pk=novedad.pk)
        if novedad.novedad_tipo_id != NOVEDAD_TIPO_VACACION:
            raise VacacionError('La novedad no es de vacaciones.')
        if novedad.dias_dinero > 0:
            raise VacacionError('La vacación tiene días en dinero: no se puede interrumpir.')
        if fecha_desde > fecha_hasta:
            raise VacacionError('La fecha desde no puede ser mayor que la fecha hasta.')
        if fecha_desde < novedad.fecha_desde or fecha_hasta > novedad.fecha_hasta:
            raise VacacionError(
                f'Las fechas deben quedar dentro de la vacación original '
                f'({novedad.fecha_desde} a {novedad.fecha_hasta}).'
            )
        if (fecha_desde, fecha_hasta) == (novedad.fecha_desde, novedad.fecha_hasta):
            raise VacacionError('Las fechas son las mismas de la vacación: no hay interrupción.')
        if not 0 < dias_disfrutados <= novedad.dias_disfrutados:
            raise VacacionError(
                f'Los días hábiles disfrutados deben ser mayores que cero y no más de {novedad.dias_disfrutados}.'
            )
        dias_rango = (fecha_hasta - fecha_desde).days + 1
        if not 0 < dias_disfrutados_reales <= dias_rango:
            raise VacacionError(
                f'Los días reales disfrutados deben ser mayores que cero y no más de {dias_rango}, '
                'los días entre las fechas.'
            )
        if novedad.estado_aprobado and contrato.fecha_ultimo_pago_vacacion != novedad.fecha_hasta_periodo:
            raise VacacionError('Solo se puede interrumpir la última vacación aprobada del contrato.')

        # La nómina paga las vacaciones por día: si ya pagó días que quedan fuera,
        # se pagarían como vacaciones y como incapacidad.
        linea = (
            GenDocumentoDetalle.objects.filter(novedad=novedad)
            .filter(Q(documento__fecha_hasta__gt=fecha_hasta) | Q(documento__fecha_desde__lt=fecha_desde))
            .select_related('documento__documento_tipo').order_by('documento__fecha_desde', 'id').first()
        )
        if linea is not None:
            documento = linea.documento
            nombre = ' '.join(
                str(parte) for parte in (documento.documento_tipo.nombre, documento.numero) if parte is not None
            )
            paso = 'desapruebe y desgenere' if documento.estado_aprobado else 'desgenere'
            raise VacacionError(
                f'La vacación ya se pagó por fuera de las nuevas fechas en el documento {documento.pk} ({nombre}); '
                f'{paso} la programación antes de interrumpirla.'
            )

        pendientes_disfrute = novedad.dias_disfrutados - dias_disfrutados

        novedad.fecha_desde = fecha_desde
        novedad.fecha_hasta = fecha_hasta
        novedad.dias_disfrutados = dias_disfrutados
        novedad.dias_disfrutados_reales = dias_disfrutados_reales
        campos = ['fecha_desde', 'fecha_hasta', 'dias_disfrutados', 'dias_disfrutados_reales']
        if novedad.estado_aprobado:
            # Las aprobadas no las encadena `recalcular_periodos`: el periodo se
            # acorta desde su mismo inicio y el contrato retrocede con él.
            novedad.fecha_hasta_periodo = sumar_dias_prestacionales(
                novedad.fecha_desde_periodo, max(_dias_periodo(dias_disfrutados), 1),
            )
            campos.append('fecha_hasta_periodo')
            contrato.fecha_ultimo_pago_vacacion = novedad.fecha_hasta_periodo
            contrato.save(update_fields=['fecha_ultimo_pago_vacacion'])
        novedad.save(update_fields=campos)
        try:
            servicio_novedad.liquidar(novedad)
        except servicio_novedad.NovedadError as e:
            raise VacacionError(e.detail)
        recalcular_periodos({contrato.pk})
        novedad.refresh_from_db()
    return novedad, pendientes_disfrute
