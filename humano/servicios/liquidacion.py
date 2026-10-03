"""
La liquidación de un contrato terminado: cesantías, intereses, prima y
vacaciones desde el último pago de cada una, más los adicionales.

Ciclo: `liquidar` (al terminar el contrato o al reliquidar) → `generar_liquidacion`
→ `aprobar_liquidacion`, y sus reversas `desgenerar_liquidacion` y
`desaprobar_liquidacion`. El documento (tipo 28, clase 701) se crea al generar,
como los de la programación, y al aprobar toma consecutivo y cartera.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from general.models import GenConfiguracion, GenDocumento, GenDocumentoDetalle
from general.servicios import documento as servicio_documento
from humano.models import HumConcepto, HumContrato, HumLiquidacion, HumLiquidacionAdicional
from humano.servicios.nomina import redondear
from utilidades.fechas import dias_prestacionales

DOCUMENTO_TIPO_LIQUIDACION = 28

CONCEPTO_VACACIONES_DINERO = 30
CONCEPTO_PRIMA_LIQUIDACION = 33
CONCEPTO_CESANTIA_LIQUIDACION = 35
CONCEPTO_INTERES_LIQUIDACION = 37

# Las prestaciones en el orden de las líneas del documento.
_PRESTACIONES = (
    ('cesantia', CONCEPTO_CESANTIA_LIQUIDACION),
    ('interes', CONCEPTO_INTERES_LIQUIDACION),
    ('prima', CONCEPTO_PRIMA_LIQUIDACION),
    ('vacacion', CONCEPTO_VACACIONES_DINERO),
)


class LiquidacionError(ValueError):
    """Un motivo por el que la liquidación no puede hacer lo que se pidió; va como `detail`."""

    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


def _bloquear(liquidacion):
    return HumLiquidacion.objects.select_for_update().select_related('contrato').get(pk=liquidacion.pk)


def _dias_desde(fecha_ultimo_pago, fecha_desde, fecha_hasta):
    """
    Días por pagar de una prestación: desde el día siguiente a su último pago o,
    si nunca se pagó, desde el inicio. Un último pago posterior al fin no deja días.
    """
    desde = fecha_ultimo_pago + timedelta(days=1) if fecha_ultimo_pago else fecha_desde
    if desde > fecha_hasta:
        return 0
    return dias_prestacionales(desde, fecha_hasta)


def _sumar_adicionales(liquidacion):
    """Deja en la liquidación la suma de sus adicionales y el total resultante (sin guardarla)."""
    adicion = deduccion = Decimal('0')
    for adicional, descuento in HumLiquidacionAdicional.objects.filter(
        liquidacion=liquidacion,
    ).values_list('adicional', 'deduccion'):
        adicion += adicional
        deduccion += descuento
    liquidacion.adicion = adicion
    liquidacion.deduccion = deduccion
    liquidacion.total = (
        liquidacion.cesantia + liquidacion.interes + liquidacion.prima + liquidacion.vacacion
        + adicion - deduccion
    )


def liquidar(liquidacion):
    """
    Calcula las prestaciones con el salario actual del contrato. Cesantías y
    prima llevan el auxilio de transporte si el contrato lo tiene; vacaciones no.
    Se puede repetir mientras la liquidación no esté generada.
    """
    configuracion = GenConfiguracion.objects.filter(pk=1).first()
    if configuracion is None:
        raise LiquidacionError('Falta la configuración general de la empresa.')

    with transaction.atomic():
        liquidacion = _bloquear(liquidacion)
        if liquidacion.estado_aprobado or liquidacion.estado_generado:
            raise LiquidacionError('La liquidación está generada o aprobada.')
        if liquidacion.fecha_hasta < liquidacion.fecha_desde:
            raise LiquidacionError('La fecha hasta de la liquidación es anterior a la fecha desde.')

        contrato = liquidacion.contrato
        desde, hasta = liquidacion.fecha_desde, liquidacion.fecha_hasta
        dias_cesantia = _dias_desde(contrato.fecha_ultimo_pago_cesantia, desde, hasta)
        dias_prima = _dias_desde(contrato.fecha_ultimo_pago_prima, desde, hasta)
        dias_vacacion = _dias_desde(contrato.fecha_ultimo_pago_vacacion, desde, hasta)

        salario = contrato.salario
        salario_prestacion = salario
        if contrato.auxilio_transporte:
            salario_prestacion += configuracion.hum_auxilio_transporte or 0

        cesantia = redondear(salario_prestacion * dias_cesantia / 360)
        # 12 % anual, proporcional a los días.
        interes = redondear(cesantia * dias_cesantia * Decimal('0.12') / 360)
        prima = redondear(salario_prestacion * dias_prima / 360)
        # 15 días hábiles por año trabajado.
        vacacion = redondear(salario * dias_vacacion / 720)

        liquidacion.dias = dias_prestacionales(desde, hasta)
        liquidacion.dias_cesantia = dias_cesantia
        liquidacion.dias_prima = dias_prima
        liquidacion.dias_vacacion = dias_vacacion
        liquidacion.cesantia = cesantia
        liquidacion.interes = interes
        liquidacion.prima = prima
        liquidacion.vacacion = vacacion
        liquidacion.salario = salario
        liquidacion.fecha_ultimo_pago = contrato.fecha_ultimo_pago
        liquidacion.fecha_ultimo_pago_cesantia = contrato.fecha_ultimo_pago_cesantia or desde
        liquidacion.fecha_ultimo_pago_prima = contrato.fecha_ultimo_pago_prima or desde
        liquidacion.fecha_ultimo_pago_vacacion = contrato.fecha_ultimo_pago_vacacion or desde
        _sumar_adicionales(liquidacion)
        liquidacion.save()
    return liquidacion


def terminar_contrato(contrato, fecha_terminacion, motivo_terminacion):
    """
    Termina el contrato en la fecha dada y crea su liquidación ya calculada.
    Todo o nada: si la liquidación no se puede calcular, el contrato sigue vigente.
    """
    with transaction.atomic():
        contrato = HumContrato.objects.select_for_update().get(pk=contrato.pk)
        if contrato.estado_terminado:
            raise LiquidacionError('El contrato ya está terminado.')
        if fecha_terminacion < contrato.fecha_desde:
            raise LiquidacionError(f'No puede terminar el contrato antes de su inicio ({contrato.fecha_desde}).')

        contrato.fecha_hasta = fecha_terminacion
        contrato.motivo_terminacion = motivo_terminacion
        contrato.estado_terminado = True
        contrato.save(update_fields=['fecha_hasta', 'motivo_terminacion', 'estado_terminado'])

        liquidacion = HumLiquidacion.objects.create(
            fecha=fecha_terminacion,
            fecha_desde=contrato.fecha_desde,
            fecha_hasta=fecha_terminacion,
            contrato=contrato,
        )
        return liquidar(liquidacion)


def actualizar_totales(liquidacion_id):
    """Vuelve a sumar los adicionales después de crear o borrar uno."""
    liquidacion = HumLiquidacion.objects.select_for_update().get(pk=liquidacion_id)
    _sumar_adicionales(liquidacion)
    liquidacion.save(update_fields=['adicion', 'deduccion', 'total'])


def _linea(documento, contacto_id, concepto, pago, operacion):
    """Una línea de nómina con las bases en las que entra el concepto (solo si devenga)."""
    detalle = GenDocumentoDetalle(
        documento=documento,
        tipo_registro='N',
        concepto=concepto,
        contacto_id=contacto_id,
        pago=pago,
        operacion=operacion,
        pago_operado=pago * operacion,
    )
    if operacion == 1:
        detalle.devengado = pago
        if concepto.ingreso_base_cotizacion:
            detalle.base_cotizacion = pago
        if concepto.ingreso_base_prestacion:
            detalle.base_prestacion = pago
        if concepto.ingreso_base_prestacion_vacacion:
            detalle.base_prestacion_vacacion = pago
    else:
        detalle.deduccion = pago
    return detalle


def generar_liquidacion(liquidacion):
    """
    Crea el documento de la liquidación con una línea por prestación y una por
    cada adicional: lo que el adicional suma devenga y lo que descuenta deduce,
    sea cual sea la operación de su concepto.
    """
    with transaction.atomic():
        liquidacion = _bloquear(liquidacion)
        if liquidacion.estado_aprobado:
            raise LiquidacionError('La liquidación está aprobada.')
        if liquidacion.estado_generado:
            raise LiquidacionError('La liquidación ya está generada.')

        contrato = liquidacion.contrato
        documento = GenDocumento.objects.create(
            liquidacion=liquidacion,
            documento_tipo_id=DOCUMENTO_TIPO_LIQUIDACION,
            fecha=liquidacion.fecha,
            fecha_vence=liquidacion.fecha,
            fecha_contable=liquidacion.fecha,
            fecha_desde=liquidacion.fecha_desde,
            fecha_hasta=liquidacion.fecha_hasta,
            contrato=contrato,
            contacto_id=contrato.contacto_id,
            salario=liquidacion.salario,
            dias=liquidacion.dias,
        )

        conceptos = HumConcepto.objects.in_bulk([concepto_id for _, concepto_id in _PRESTACIONES])
        lineas = [
            _linea(documento, contrato.contacto_id, conceptos[concepto_id], getattr(liquidacion, campo), 1)
            for campo, concepto_id in _PRESTACIONES
            if getattr(liquidacion, campo) > 0
        ]
        for adicional in HumLiquidacionAdicional.objects.filter(liquidacion=liquidacion).select_related('concepto').order_by('id'):
            if adicional.adicional > 0:
                lineas.append(_linea(documento, contrato.contacto_id, adicional.concepto, adicional.adicional, 1))
            if adicional.deduccion > 0:
                lineas.append(_linea(documento, contrato.contacto_id, adicional.concepto, adicional.deduccion, -1))
        GenDocumentoDetalle.objects.bulk_create(lineas)

        documento.devengado = sum((linea.devengado for linea in lineas if linea.operacion == 1), Decimal('0'))
        documento.deduccion = sum((linea.deduccion for linea in lineas if linea.operacion == -1), Decimal('0'))
        documento.total = documento.devengado - documento.deduccion
        documento.base_cotizacion = sum((linea.base_cotizacion or 0 for linea in lineas), Decimal('0'))
        documento.base_prestacion = sum((linea.base_prestacion or 0 for linea in lineas), Decimal('0'))
        documento.base_prestacion_vacacion = sum(
            (linea.base_prestacion_vacacion or 0 for linea in lineas), Decimal('0'),
        )
        documento.save(update_fields=[
            'devengado', 'deduccion', 'total',
            'base_cotizacion', 'base_prestacion', 'base_prestacion_vacacion',
        ])

        _sumar_adicionales(liquidacion)
        liquidacion.estado_generado = True
        liquidacion.save(update_fields=['adicion', 'deduccion', 'total', 'estado_generado'])
    return liquidacion


def desgenerar_liquidacion(liquidacion):
    """Borra el documento de la liquidación; los valores calculados se conservan."""
    with transaction.atomic():
        liquidacion = _bloquear(liquidacion)
        if liquidacion.estado_aprobado:
            raise LiquidacionError('La liquidación está aprobada.')
        if not liquidacion.estado_generado:
            raise LiquidacionError('La liquidación no está generada.')

        documentos = GenDocumento.objects.filter(liquidacion=liquidacion)
        GenDocumentoDetalle.objects.filter(documento__in=documentos).delete()
        documentos.delete()

        liquidacion.estado_generado = False
        liquidacion.save(update_fields=['estado_generado'])
    return liquidacion


def aprobar_liquidacion(liquidacion):
    """Aprueba el documento: consecutivo y cartera los pone `general.servicios.documento.aprobar`."""
    with transaction.atomic():
        liquidacion = _bloquear(liquidacion)
        if liquidacion.estado_aprobado:
            raise LiquidacionError('La liquidación ya está aprobada.')
        if not liquidacion.estado_generado:
            raise LiquidacionError('La liquidación no está generada.')
        if liquidacion.total < 0:
            raise LiquidacionError('El total de la liquidación es negativo.')

        try:
            for documento_id in GenDocumento.objects.filter(liquidacion=liquidacion).order_by('id').values_list('id', flat=True):
                servicio_documento.aprobar(documento_id)
        except ValidationError as e:
            raise LiquidacionError(_mensaje(e))

        liquidacion.estado_aprobado = True
        liquidacion.save(update_fields=['estado_aprobado'])
    return liquidacion


def desaprobar_liquidacion(liquidacion):
    """Deshace `aprobar_liquidacion`. No se puede si el documento ya tiene un egreso o está contabilizado."""
    with transaction.atomic():
        liquidacion = _bloquear(liquidacion)
        if not liquidacion.estado_aprobado:
            raise LiquidacionError('La liquidación no está aprobada.')

        documentos = list(GenDocumento.objects.filter(liquidacion=liquidacion).order_by('id'))
        for documento in documentos:
            if documento.afectado > 0:
                raise LiquidacionError(
                    f'El documento {documento.numero} ya tiene un egreso: no se puede desaprobar la liquidación.'
                )
        try:
            for documento in documentos:
                servicio_documento.desaprobar(documento.id)
        except ValidationError as e:
            raise LiquidacionError(_mensaje(e))

        liquidacion.estado_aprobado = False
        liquidacion.save(update_fields=['estado_aprobado'])
    return liquidacion


def _mensaje(error):
    """El texto de un `ValidationError` de DRF, que puede venir como lista o dict."""
    detalle = error.detail
    if isinstance(detalle, list) and detalle:
        return str(detalle[0])
    if isinstance(detalle, dict) and detalle:
        primero = next(iter(detalle.values()))
        return str(primero[0] if isinstance(primero, list) and primero else primero)
    return str(detalle)
