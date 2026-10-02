from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q, Sum

from django.db.models import Max
from rest_framework.exceptions import ValidationError

from general.models import GenConfiguracion, GenDocumento, GenDocumentoDetalle
from general.servicios import documento as servicio_documento
from humano.models import HumContrato, HumCredito, HumNovedad, HumProgramacion, HumProgramacionDetalle
from humano.servicios.nomina import (
    DOCUMENTO_TIPO_POR_PAGO_TIPO,
    PAGO_TIPO_CESANTIA,
    PAGO_TIPO_INTERES,
    PAGO_TIPO_NOMINA,
    PAGO_TIPO_PRIMA,
    ContextoNomina,
    NominaError,
    liquidar_detalle,
)
from utilidades.fechas import dias_prestacionales

# La fecha de último pago del contrato que mueve cada tipo de pago al aprobar.
# Los intereses de cesantía no tienen una propia.
FECHA_ULTIMO_PAGO_POR_PAGO_TIPO = {
    PAGO_TIPO_NOMINA: 'fecha_ultimo_pago',
    PAGO_TIPO_PRIMA: 'fecha_ultimo_pago_prima',
    PAGO_TIPO_CESANTIA: 'fecha_ultimo_pago_cesantia',
}

CONTRATO_TIPO_INDEFINIDO = 1
# Práctica estudiantil: no cotiza salud ni pensión y no recibe auxilio de transporte.
CONTRATO_TIPO_PRACTICA = 5
PENSION_PENSIONADO = 4
TIEMPO_MEDIO = 2
DOCUMENTO_CLASE_NOMINA = 701
CONCEPTO_FONDO_SOLIDARIDAD = 20

# Banderas que el detalle hereda de la programación tal cual.
_BANDERAS = (
    'pago_horas', 'pago_auxilio_transporte', 'pago_incapacidad', 'pago_licencia',
    'pago_vacacion', 'descuento_salud', 'descuento_pension', 'descuento_fondo_solidaridad',
    'descuento_retencion_fuente', 'descuento_credito', 'descuento_embargo', 'adicional',
)


class ProgramacionError(ValueError):
    """
    Un motivo por el que la programación no puede hacer lo que se pidió; va como
    `detail`. `errores` lleva el detalle por contrato cuando hay más de uno.
    """

    def __init__(self, detail, errores=None):
        self.detail = detail
        self.errores = errores or []
        super().__init__(detail)


def cargar_contratos(programacion):
    """
    Crea un `HumProgramacionDetalle` por cada contrato del grupo de la programación
    que le aplique según el tipo de pago (nómina, prima, cesantía o intereses).

    Los contratos que ya tienen detalle en la programación se saltan, así que se
    puede llamar varias veces para recoger contratos nuevos. Todo o nada: si falla,
    no queda ningún detalle a medias.

    Retorna la cantidad de detalles creados.
    """
    configuracion = GenConfiguracion.objects.filter(pk=1).first()
    if configuracion is None:
        raise ProgramacionError('Falta la configuración general de la empresa.')

    with transaction.atomic():
        # Bloqueada: dos cargas a la vez verían los mismos contratos sin detalle y
        # los crearían dos veces.
        programacion = HumProgramacion.objects.select_for_update().get(pk=programacion.pk)
        if programacion.estado_generado:
            raise ProgramacionError('La programación ya está generada.')
        existentes = set(
            HumProgramacionDetalle.objects.filter(programacion=programacion)
            .values_list('contrato_id', flat=True)
        )
        if programacion.pago_tipo_id == PAGO_TIPO_NOMINA:
            detalles = _detalles_nomina(programacion, configuracion, existentes)
        elif programacion.pago_tipo_id == PAGO_TIPO_PRIMA:
            detalles = _detalles_prima(programacion, configuracion, existentes)
        elif programacion.pago_tipo_id in (PAGO_TIPO_CESANTIA, PAGO_TIPO_INTERES):
            detalles = _detalles_cesantia(programacion, configuracion, existentes)
        else:
            detalles = []

        HumProgramacionDetalle.objects.bulk_create(detalles)
        programacion.contratos = len(existentes) + len(detalles)
        programacion.save(update_fields=['contratos'])
    return len(detalles)


def eliminar_detalles(programacion, ids=None):
    """
    Borra los detalles de la programación: los de `ids` o, sin `ids`, todos.
    Un id que no sea de esta programación se ignora. Recuenta `contratos`.

    Retorna la cantidad de detalles eliminados.
    """
    with transaction.atomic():
        programacion = HumProgramacion.objects.select_for_update().get(pk=programacion.pk)
        if programacion.estado_aprobado:
            raise ProgramacionError('La programación está aprobada.')
        if programacion.estado_generado:
            raise ProgramacionError('La programación está generada: desgenérela antes de eliminar detalles.')

        detalles = HumProgramacionDetalle.objects.filter(programacion=programacion)
        if ids is not None:
            detalles = detalles.filter(id__in=ids)
        eliminados, _ = detalles.delete()

        programacion.contratos = HumProgramacionDetalle.objects.filter(programacion=programacion).count()
        programacion.save(update_fields=['contratos'])
    return eliminados


def _detalle_base(programacion, contrato):
    """Lo común a todos los tipos de pago: contrato, salario, banderas e ingreso."""
    detalle = HumProgramacionDetalle(
        programacion=programacion,
        contrato=contrato,
        salario=contrato.salario,
        ingreso=programacion.fecha_desde <= contrato.fecha_desde <= programacion.fecha_hasta_periodo,
    )
    for bandera in _BANDERAS:
        setattr(detalle, bandera, getattr(programacion, bandera))
    return detalle


def _contratos_vigentes(programacion, existentes):
    """Los contratos sin terminar del grupo que arrancaron antes del cierre del periodo."""
    return HumContrato.objects.filter(
        grupo_id=programacion.grupo_id,
        fecha_desde__lte=programacion.fecha_hasta_periodo,
        estado_terminado=False,
    ).exclude(id__in=existentes)


def _sumas_por_contrato(campo, **filtros):
    """`{contrato_id: suma de campo}` sobre los detalles de documentos aprobados."""
    return dict(
        GenDocumentoDetalle.objects.filter(documento__estado_aprobado=True, **filtros)
        .values('documento__contrato_id')
        .annotate(total=Sum(campo))
        .values_list('documento__contrato_id', 'total')
    )


def _detalles_nomina(programacion, configuracion, existentes):
    contratos = list(HumContrato.objects.filter(
        Q(fecha_ultimo_pago__isnull=True)
        | Q(fecha_ultimo_pago__lt=programacion.fecha_hasta)
        | Q(fecha_desde=programacion.fecha_hasta_periodo)
        | Q(fecha_desde=programacion.fecha_hasta),
        Q(fecha_hasta__gte=programacion.fecha_desde) | Q(estado_terminado=False),
        grupo_id=programacion.grupo_id,
        fecha_desde__lte=programacion.fecha_hasta_periodo,
    ).exclude(id__in=existentes))
    if not contratos:
        return []
    ids = [contrato.id for contrato in contratos]

    novedades = {}
    for novedad in HumNovedad.objects.filter(
        contrato_id__in=ids,
        fecha_desde__lte=programacion.fecha_hasta,
        fecha_hasta__gte=programacion.fecha_desde,
    ):
        novedades.setdefault(novedad.contrato_id, []).append(novedad)

    # Lo ya liquidado en el mes de la programación, para los topes de cotización.
    mes_desde = programacion.fecha_desde.replace(day=1)
    mes_hasta = mes_desde + relativedelta(months=1, days=-1)
    del_mes = {
        'documento__contrato_id__in': ids,
        'documento__fecha__gte': mes_desde,
        'documento__fecha__lte': mes_hasta,
    }
    base_cotizacion = _sumas_por_contrato(
        'base_cotizacion', documento__documento_tipo__documento_clase_id=DOCUMENTO_CLASE_NOMINA, **del_mes,
    )
    fondo_solidaridad = _sumas_por_contrato('pago', concepto_id=CONCEPTO_FONDO_SOLIDARIDAD, **del_mes)

    factor = configuracion.hum_factor
    detalles = []
    for contrato in contratos:
        detalle = _detalle_base(programacion, contrato)
        detalle.retiro = (
            contrato.estado_terminado
            and programacion.fecha_desde <= contrato.fecha_hasta <= programacion.fecha_hasta_periodo
        )
        if contrato.contrato_tipo_id == CONTRATO_TIPO_PRACTICA:
            detalle.descuento_salud = False
            detalle.descuento_pension = False
            detalle.pago_auxilio_transporte = False
        if contrato.pension_id == PENSION_PENSIONADO:
            detalle.descuento_pension = False

        fecha_desde = max(contrato.fecha_desde, programacion.fecha_desde)
        fecha_hasta = contrato.fecha_hasta
        error_terminacion = False
        if not contrato.estado_terminado:
            if contrato.contrato_tipo_id == CONTRATO_TIPO_INDEFINIDO:
                fecha_hasta = programacion.fecha_hasta
            elif contrato.fecha_hasta < programacion.fecha_desde:
                # Contrato a término vencido que nadie terminó: no se le paga.
                fecha_hasta = programacion.fecha_desde
                error_terminacion = True
        fecha_hasta = min(fecha_hasta, programacion.fecha_hasta)

        dias_novedad = 0
        for novedad in novedades.get(contrato.id, ()):
            desde = max(novedad.fecha_desde, fecha_desde)
            hasta = min(novedad.fecha_hasta, fecha_hasta)
            # Una novedad del periodo que cae fuera de las fechas del contrato no resta.
            dias_novedad += max((hasta - desde).days + 1, 0)

        dias = (fecha_hasta - fecha_desde).days + 1 - dias_novedad
        # Febrero completo se paga como 30 días.
        if (
            programacion.fecha_desde.month == 2 and programacion.fecha_hasta.month == 2
            and dias + dias_novedad == programacion.dias_reales
        ):
            if programacion.fecha_hasta.day == 28:
                dias += 2
            elif programacion.fecha_hasta.day == 29:
                dias += 1
        if dias < 0 or error_terminacion:
            dias = 0

        detalle.fecha_desde = fecha_desde
        detalle.fecha_hasta = fecha_hasta
        detalle.error_terminacion = error_terminacion
        detalle.dias = dias
        detalle.dias_transporte = dias
        detalle.dias_novedad = dias_novedad
        if contrato.tiempo_id == TIEMPO_MEDIO:
            detalle.diurna = round(dias * (factor / 2), 3)
        else:
            detalle.diurna = dias * factor
        detalle.base_cotizacion_acumulado = base_cotizacion.get(contrato.id) or 0
        detalle.deduccion_fondo_pension_acumulado = fondo_solidaridad.get(contrato.id) or 0
        detalles.append(detalle)
    return detalles


def _fechas_prestacion(programacion, contrato):
    """Fechas del detalle en prima y cesantía: el indefinido llega hasta el final."""
    fecha_desde = max(contrato.fecha_desde, programacion.fecha_desde)
    fecha_hasta = contrato.fecha_hasta
    if contrato.contrato_tipo_id == CONTRATO_TIPO_INDEFINIDO:
        fecha_hasta = programacion.fecha_hasta
    return fecha_desde, min(fecha_hasta, programacion.fecha_hasta)


def _detalles_prima(programacion, configuracion, existentes):
    detalles = []
    for contrato in _contratos_vigentes(programacion, existentes):
        detalle = _detalle_base(programacion, contrato)
        detalle.fecha_desde, detalle.fecha_hasta = _fechas_prestacion(programacion, contrato)
        detalle.dias = dias_prestacionales(detalle.fecha_desde, detalle.fecha_hasta)
        detalle.dias_transporte = 0
        detalle.salario_promedio = contrato.salario
        if contrato.auxilio_transporte:
            detalle.salario_promedio += configuracion.hum_auxilio_transporte
        detalles.append(detalle)
    return detalles


def _detalles_cesantia(programacion, configuracion, existentes):
    contratos = list(_contratos_vigentes(programacion, existentes))
    if not contratos:
        return []
    base_prestacion = _sumas_por_contrato(
        'base_prestacion',
        documento__documento_tipo__documento_clase_id=DOCUMENTO_CLASE_NOMINA,
        documento__contrato_id__in=[contrato.id for contrato in contratos],
        documento__fecha__gte=programacion.fecha_desde,
        documento__fecha__lte=programacion.fecha_hasta_periodo,
    )

    detalles = []
    for contrato in contratos:
        detalle = _detalle_base(programacion, contrato)
        detalle.fecha_desde, detalle.fecha_hasta = _fechas_prestacion(programacion, contrato)
        dias = dias_prestacionales(detalle.fecha_desde, detalle.fecha_hasta)
        base = base_prestacion.get(contrato.id) or Decimal(0)

        auxilio = configuracion.hum_auxilio_transporte if contrato.auxilio_transporte else 0
        salario_promedio = base / dias * 30 if dias > 0 else Decimal(0)
        if programacion.base_prestacion_minimo and salario_promedio < configuracion.hum_salario_minimo:
            salario_promedio = configuracion.hum_salario_minimo + auxilio
        if programacion.base_prestacion_minimo_salario and salario_promedio < contrato.salario:
            salario_promedio = contrato.salario + auxilio

        detalle.dias = dias
        detalle.dias_transporte = 0
        detalle.base_prestacion = base
        detalle.salario_promedio = round(salario_promedio)
        detalles.append(detalle)
    return detalles


def _bloquear(programacion):
    """La programación con su fila bloqueada hasta el final de la transacción."""
    return HumProgramacion.objects.select_for_update().get(pk=programacion.pk)


def _documentos(programacion):
    return GenDocumento.objects.filter(programacion_detalle__programacion=programacion)


def generar_programacion(programacion):
    """
    Liquida la programación: un documento de nómina por detalle, con sus líneas,
    y los totales en cada detalle y en la programación.
    """
    configuracion = GenConfiguracion.objects.filter(pk=1).first()
    if configuracion is None:
        raise ProgramacionError('Falta la configuración general de la empresa.')
    if not configuracion.hum_factor or not configuracion.hum_salario_minimo:
        raise ProgramacionError('Falta el factor de horas o el salario mínimo en la configuración.')

    with transaction.atomic():
        programacion = _bloquear(programacion)
        if programacion.estado_aprobado:
            raise ProgramacionError('La programación está aprobada.')
        if programacion.estado_generado:
            raise ProgramacionError('La programación ya está generada.')
        if programacion.pago_tipo_id not in DOCUMENTO_TIPO_POR_PAGO_TIPO:
            raise ProgramacionError('El tipo de pago de la programación no se puede generar.')

        detalles = list(
            HumProgramacionDetalle.objects.filter(programacion=programacion).select_related(
                'contrato__tipo_cotizante', 'contrato__salud__concepto', 'contrato__pension__concepto',
                'contrato__entidad_salud', 'contrato__entidad_pension',
            ).order_by('id')
        )
        if not detalles:
            raise ProgramacionError('La programación no tiene detalles.')

        contexto = ContextoNomina.cargar(programacion, configuracion, [d.contrato for d in detalles])
        try:
            for detalle in detalles:
                liquidar_detalle(contexto, detalle)
        except NominaError as e:
            raise ProgramacionError(e.detail)
        HumProgramacionDetalle.objects.bulk_update(detalles, ['devengado', 'deduccion', 'total'])

        programacion.devengado = sum(d.devengado for d in detalles)
        programacion.deduccion = sum(d.deduccion for d in detalles)
        programacion.total = sum(d.total for d in detalles)
        programacion.estado_generado = True
        programacion.save(update_fields=['devengado', 'deduccion', 'total', 'estado_generado'])
    return programacion


def desgenerar_programacion(programacion):
    """Borra los documentos de la programación y deja sus totales en cero."""
    with transaction.atomic():
        programacion = _bloquear(programacion)
        if programacion.estado_aprobado:
            raise ProgramacionError('La programación está aprobada.')
        if not programacion.estado_generado:
            raise ProgramacionError('La programación no está generada.')

        documentos = _documentos(programacion)
        GenDocumentoDetalle.objects.filter(documento__in=documentos).delete()
        documentos.delete()
        HumProgramacionDetalle.objects.filter(programacion=programacion).update(
            devengado=0, deduccion=0, total=0,
        )

        programacion.devengado = 0
        programacion.deduccion = 0
        programacion.total = 0
        programacion.estado_generado = False
        programacion.save(update_fields=['devengado', 'deduccion', 'total', 'estado_generado'])
    return programacion


def _afectar_creditos(programacion, signo):
    """Abona (o desabona, con `signo` -1) a cada crédito lo que le descontó la programación."""
    lineas = GenDocumentoDetalle.objects.filter(
        documento__programacion_detalle__programacion=programacion, credito__isnull=False,
    )
    pagos = {}
    for credito_id, pago in lineas.values_list('credito_id', 'pago'):
        cuotas, total = pagos.get(credito_id, (0, Decimal('0')))
        pagos[credito_id] = (cuotas + 1, total + pago)
    for credito in HumCredito.objects.select_for_update().filter(id__in=pagos):
        cuotas, total = pagos[credito.id]
        credito.abono += total * signo
        credito.saldo -= total * signo
        credito.cuota_actual += cuotas * signo
        credito.save(update_fields=['abono', 'saldo', 'cuota_actual'])


def aprobar_programacion(programacion):
    """
    Aprueba cada documento de la programación (consecutivo y cartera los pone
    `general.servicios.documento.aprobar`), abona los créditos descontados y
    mueve la fecha de último pago de los contratos.
    """
    with transaction.atomic():
        programacion = _bloquear(programacion)
        if programacion.estado_aprobado:
            raise ProgramacionError('La programación ya está aprobada.')
        if not programacion.estado_generado:
            raise ProgramacionError('La programación no está generada.')

        detalles = list(
            HumProgramacionDetalle.objects.filter(programacion=programacion)
            .select_related('contrato__contacto').order_by('id')
        )
        if not detalles:
            raise ProgramacionError('La programación no tiene detalles.')
        errores = []
        for detalle in detalles:
            contrato = {'contrato_id': detalle.contrato_id, 'contrato': detalle.contrato.contacto.nombre_corto}
            if detalle.error_terminacion:
                errores.append({**contrato, 'mensaje': (
                    'El contrato tiene fecha de terminación anterior a la programación y no está terminado.'
                )})
            if detalle.total < 0:
                errores.append({**contrato, 'mensaje': 'El total del detalle es negativo.'})
        if errores:
            raise ProgramacionError('La programación tiene inconsistencias.', errores)

        try:
            for documento_id in _documentos(programacion).order_by('id').values_list('id', flat=True):
                servicio_documento.aprobar(documento_id)
        except ValidationError as e:
            raise ProgramacionError(_mensaje(e))
        _afectar_creditos(programacion, signo=1)

        campo = FECHA_ULTIMO_PAGO_POR_PAGO_TIPO.get(programacion.pago_tipo_id)
        if campo:
            HumContrato.objects.filter(id__in=[d.contrato_id for d in detalles]).update(
                **{campo: programacion.fecha_hasta},
            )

        programacion.estado_aprobado = True
        programacion.save(update_fields=['estado_aprobado'])
    return programacion


def desaprobar_programacion(programacion):
    """
    Deshace `aprobar_programacion`. No se puede si algún documento ya tiene pagos
    o está contabilizado. La fecha de último pago de cada contrato vuelve a la de
    su programación aprobada anterior del mismo tipo de pago.
    """
    with transaction.atomic():
        programacion = _bloquear(programacion)
        if not programacion.estado_aprobado:
            raise ProgramacionError('La programación no está aprobada.')

        documentos = list(_documentos(programacion).order_by('id'))
        for documento in documentos:
            if documento.afectado > 0:
                raise ProgramacionError(
                    f'El documento {documento.numero} ya tiene un egreso: no se puede desaprobar la programación.'
                )
        try:
            for documento in documentos:
                servicio_documento.desaprobar(documento.id)
        except ValidationError as e:
            raise ProgramacionError(_mensaje(e))
        _afectar_creditos(programacion, signo=-1)

        campo = FECHA_ULTIMO_PAGO_POR_PAGO_TIPO.get(programacion.pago_tipo_id)
        if campo:
            contrato_ids = [documento.contrato_id for documento in documentos]
            anteriores = dict(
                GenDocumento.objects.filter(
                    contrato_id__in=contrato_ids,
                    estado_aprobado=True,
                    programacion_detalle__programacion__pago_tipo_id=programacion.pago_tipo_id,
                )
                .values('contrato_id')
                .annotate(fecha=Max('programacion_detalle__programacion__fecha_hasta'))
                .values_list('contrato_id', 'fecha')
            )
            contratos = list(HumContrato.objects.filter(id__in=contrato_ids))
            for contrato in contratos:
                setattr(contrato, campo, anteriores.get(contrato.id))
            HumContrato.objects.bulk_update(contratos, [campo])

        programacion.estado_aprobado = False
        programacion.save(update_fields=['estado_aprobado'])
    return programacion


def _mensaje(error):
    """El texto de un `ValidationError` de DRF, que puede venir como lista o dict."""
    detalle = error.detail
    if isinstance(detalle, list) and detalle:
        return str(detalle[0])
    if isinstance(detalle, dict) and detalle:
        primero = next(iter(detalle.values()))
        return str(primero[0] if isinstance(primero, list) and primero else primero)
    return str(detalle)
