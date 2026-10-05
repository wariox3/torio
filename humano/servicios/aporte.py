"""
El aporte a seguridad social (PILA) de un mes: qué contratos entran, cuánto se
cotiza a cada subsistema y los documentos por pagar a cada entidad.

Ciclo: `cargar_contratos_aporte` (y `eliminar_contrato_aporte`) → `generar_aporte` → `aprobar_aporte`, y sus
reversas `desgenerar_aporte` y `desaprobar_aporte`. La base sale de la nómina
**aprobada** del mes (documentos clase 701): una programación generada pero sin
aprobar todavía puede cambiar.
"""
import math
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from rest_framework.exceptions import ValidationError

from general.models import GenConfiguracion, GenContacto, GenDocumento, GenDocumentoDetalle
from general.servicios import documento as servicio_documento
from humano.models import HumAporte, HumAporteContrato, HumAporteDetalle, HumAporteEntidad, HumContrato
from humano.servicios.nomina import porcentaje_fondo_solidaridad

DOCUMENTO_CLASE_NOMINA = 701
DOCUMENTO_TIPO_SEGURIDAD_SOCIAL = 22
CONTRATO_TIPO_INDEFINIDO = 1

CONCEPTO_SALUD = 14
CONCEPTO_PENSION = 15
CONCEPTO_FONDO_SOLIDARIDAD = 20
# Vacaciones en dinero: no son tiempo de vacaciones y no cotizan.
CONCEPTO_VACACIONES_DINERO = 30

NOVEDAD_INCAPACIDAD_GENERAL = 1
NOVEDAD_INCAPACIDAD_LABORAL = 2
NOVEDAD_LICENCIA_MATERNIDAD = 3
NOVEDADES_LICENCIA_REMUNERADA = (4, 5)
NOVEDAD_LICENCIA_NO_REMUNERADA = 6
NOVEDAD_VACACIONES = 7

TARIFA_PENSION = Decimal('16')
TARIFA_PENSION_EMPLEADOR = Decimal('12')
TARIFA_SALUD = Decimal('4')
TARIFA_SALUD_SIN_PENSION = Decimal('12.5')
TARIFA_CAJA = Decimal('4')
# Del porcentaje del fondo de solidaridad, esto va a la subcuenta de solidaridad;
# el resto, a la de subsistencia.
FONDO_SUBCUENTA_SOLIDARIDAD = Decimal('0.5')
HORAS_DIA = 8

# Tipos de cotizante que no cotizan pensión ni caja y pagan salud completa:
# aprendices SENA en etapa lectiva y estudiantes. Por código PILA y no por id,
# porque el id depende del catálogo de cada sistema.
TIPOS_COTIZANTE_SIN_PENSION = ('12', '19', '20', '23')

# Las entidades a las que se les paga, en el orden de los documentos.
TIPOS_ENTIDAD = ('PENSION', 'SALUD', 'CAJA', 'RIESGO', 'SENA', 'ICBF')

# Lo que se acumula de los detalles hacia el contrato y el aporte.
_COTIZACIONES = (
    'cotizacion_pension', 'cotizacion_solidaridad_solidaridad', 'cotizacion_solidaridad_subsistencia',
    'cotizacion_voluntario_pension_afiliado', 'cotizacion_voluntario_pension_aportante',
    'cotizacion_salud', 'cotizacion_riesgos', 'cotizacion_caja', 'cotizacion_sena', 'cotizacion_icbf',
    'cotizacion_total',
)


class AporteError(ValueError):
    """
    Un motivo por el que el aporte no puede hacer lo que se pidió; va como
    `detail`. `errores` lleva el detalle por entidad cuando hay más de uno.
    """

    def __init__(self, detail, errores=None):
        self.detail = detail
        self.errores = errores or []
        super().__init__(detail)


def redondear_cien(valor):
    """Las cotizaciones de la PILA se aproximan al múltiplo de 100 superior."""
    return Decimal(math.ceil(Decimal(valor) / 100) * 100)


def _bloquear(aporte):
    return HumAporte.objects.select_for_update().get(pk=aporte.pk)


def _configuracion():
    configuracion = GenConfiguracion.objects.filter(pk=1).first()
    if configuracion is None or not configuracion.hum_salario_minimo:
        raise AporteError('Falta el salario mínimo en la configuración general.')
    return configuracion


def _documentos_nomina(**filtros):
    """Detalles de la nómina aprobada (documentos clase 701)."""
    return GenDocumentoDetalle.objects.filter(
        documento__documento_tipo__documento_clase_id=DOCUMENTO_CLASE_NOMINA,
        documento__estado_aprobado=True,
        **filtros,
    )


# ------------------------------------------------------------ cargar ----

def cargar_contratos_aporte(aporte):
    """
    Agrega al aporte un `HumAporteContrato` por cada contrato de la sucursal que
    estuvo vigente en el mes, con sus días, su IBC y lo que ya se le descontó al
    empleado de salud y pensión en la nómina. Los que ya están se saltan.

    Retorna la cantidad de contratos agregados.
    """
    with transaction.atomic():
        aporte = _bloquear(aporte)
        if aporte.estado_aprobado or aporte.estado_generado:
            raise AporteError('El aporte está generado o aprobado.')
        if aporte.sucursal_id is None:
            raise AporteError('El aporte no tiene sucursal.')

        contratos = HumContrato.objects.filter(
            Q(fecha_hasta__gte=aporte.fecha_desde) | Q(estado_terminado=False),
            fecha_desde__lte=aporte.fecha_hasta_periodo,
            sucursal_id=aporte.sucursal_id,
        )
        existentes = set(
            HumAporteContrato.objects.filter(aporte=aporte).values_list('contrato_id', flat=True)
        )
        nuevos = [contrato for contrato in contratos if contrato.id not in existentes]

        # Lo de la nómina del mes, por contrato y fecha del documento: cada
        # contrato suma solo lo que cae dentro de sus propias fechas.
        nomina = defaultdict(list)
        filas = (
            _documentos_nomina(
                documento__contrato_id__in=[contrato.id for contrato in nuevos],
                documento__fecha__gte=aporte.fecha_desde,
                documento__fecha__lte=aporte.fecha_hasta,
            )
            .values('documento__contrato_id', 'documento__fecha', 'concepto_id')
            .annotate(ibc=Sum('base_cotizacion'), pago=Sum('pago'))
        )
        for fila in filas:
            nomina[fila['documento__contrato_id']].append(fila)

        aporte_contratos = []
        for contrato in nuevos:
            fecha_desde = max(contrato.fecha_desde, aporte.fecha_desde)
            fecha_hasta = contrato.fecha_hasta
            error_terminacion = False
            if not contrato.estado_terminado:
                if contrato.contrato_tipo_id == CONTRATO_TIPO_INDEFINIDO:
                    fecha_hasta = aporte.fecha_hasta
                elif contrato.fecha_hasta < aporte.fecha_desde:
                    # A término vencido y nadie lo terminó: no cotiza.
                    fecha_hasta = aporte.fecha_desde
                    error_terminacion = True
            fecha_hasta = min(fecha_hasta, aporte.fecha_hasta)

            dias = (fecha_hasta - fecha_desde).days + 1
            # Febrero completo cotiza 30 días.
            if fecha_desde.month == 2 and fecha_hasta == aporte.fecha_hasta_periodo and aporte.mes == 2:
                dias += 30 - fecha_hasta.day
            if error_terminacion:
                dias = 0

            ibc = pension_empleado = salud_empleado = Decimal('0')
            for fila in nomina.get(contrato.id, ()):
                if not fecha_desde <= fila['documento__fecha'] <= fecha_hasta:
                    continue
                ibc += fila['ibc'] or 0
                if fila['concepto_id'] in (CONCEPTO_PENSION, CONCEPTO_FONDO_SOLIDARIDAD):
                    pension_empleado += fila['pago'] or 0
                elif fila['concepto_id'] == CONCEPTO_SALUD:
                    salud_empleado += fila['pago'] or 0

            aporte_contratos.append(HumAporteContrato(
                aporte=aporte,
                contrato=contrato,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                dias=dias,
                salario=contrato.salario,
                base_cotizacion=ibc,
                cotizacion_pension_empleado=pension_empleado,
                cotizacion_salud_empleado=salud_empleado,
                ingreso=aporte.fecha_desde <= contrato.fecha_desde <= aporte.fecha_hasta_periodo,
                retiro=(
                    contrato.estado_terminado
                    and aporte.fecha_desde <= contrato.fecha_hasta <= aporte.fecha_hasta_periodo
                ),
                error_terminacion=error_terminacion,
                ciudad_labora_id=contrato.ciudad_labora_id,
                entidad_salud_id=contrato.entidad_salud_id,
                entidad_pension_id=contrato.entidad_pension_id,
                entidad_caja_id=contrato.entidad_caja_id,
                entidad_riesgo_id=aporte.entidad_riesgo_id,
                entidad_sena_id=aporte.entidad_sena_id,
                entidad_icbf_id=aporte.entidad_icbf_id,
                riesgo_id=contrato.riesgo_id,
            ))
        HumAporteContrato.objects.bulk_create(aporte_contratos)
        _contar_contratos(aporte)
    return len(aporte_contratos)


def eliminar_contrato_aporte(aporte_contrato):
    """
    Quita un contrato del aporte. Solo mientras el aporte no esté generado: una
    vez generado, los detalles y los totales salen de sus contratos.
    """
    with transaction.atomic():
        aporte = _bloquear(aporte_contrato.aporte)
        if aporte.estado_generado:
            raise AporteError('El aporte está generado: desgenérelo antes de eliminar contratos.')
        aporte_contrato.delete()
        _contar_contratos(aporte)


def _contar_contratos(aporte):
    cargados = HumAporteContrato.objects.filter(aporte=aporte)
    aporte.contratos = cargados.count()
    aporte.empleados = cargados.values('contrato__contacto_id').distinct().count()
    aporte.save(update_fields=['contratos', 'empleados'])


# ----------------------------------------------------------- generar ----

def generar_aporte(aporte):
    """
    Liquida el aporte: una línea (`HumAporteDetalle`) por cada novedad del mes y
    otra por los días restantes de cada contrato, los totales por contrato y del
    aporte, y lo que se le debe a cada entidad.
    """
    configuracion = _configuracion()
    with transaction.atomic():
        aporte = _bloquear(aporte)
        if aporte.estado_aprobado:
            raise AporteError('El aporte está aprobado.')
        if aporte.estado_generado:
            raise AporteError('El aporte ya está generado.')
        aporte_contratos = list(
            HumAporteContrato.objects.filter(aporte=aporte)
            .select_related('contrato__tipo_cotizante', 'riesgo').order_by('id')
        )
        if not aporte_contratos:
            raise AporteError('El aporte no tiene contratos.')

        # La nómina del mes por contrato y novedad: una fila por novedad y otra
        # con todo lo que no es novedad (`novedad_id` nulo).
        nomina = defaultdict(list)
        filas = (
            _documentos_nomina(
                documento__contrato_id__in=[ac.contrato_id for ac in aporte_contratos],
                documento__fecha__gte=aporte.fecha_desde,
                documento__fecha__lte=aporte.fecha_hasta,
            )
            .exclude(concepto_id=CONCEPTO_VACACIONES_DINERO)
            .values(
                'documento__contrato_id', 'novedad_id', 'novedad__novedad_tipo_id',
                'novedad__fecha_desde', 'novedad__fecha_hasta',
            )
            .annotate(base_cotizacion=Sum('base_cotizacion'), dias=Sum('dias'))
            .order_by('documento__contrato_id', 'novedad_id')
        )
        for fila in filas:
            nomina[fila['documento__contrato_id']].append(fila)

        base_total = Decimal('0')
        detalles = []
        for aporte_contrato in aporte_contratos:
            lineas_contrato, base_contrato = _liquidar_contrato(
                aporte, aporte_contrato, nomina.get(aporte_contrato.contrato_id, ()), configuracion,
            )
            detalles.extend(lineas_contrato)
            base_total += base_contrato
        HumAporteDetalle.objects.bulk_create(detalles)

        _totalizar(aporte, aporte_contratos, detalles)
        aporte.base_cotizacion = base_total
        aporte.lineas = len(detalles)
        aporte.contratos = len(aporte_contratos)
        aporte.empleados = len({ac.contrato.contacto_id for ac in aporte_contratos})
        aporte.estado_generado = True
        aporte.save()

        _crear_entidades(aporte)
    return aporte


def _recortar(desde, hasta, aporte):
    """Las fechas de la novedad dentro del mes del aporte."""
    return max(desde, aporte.fecha_desde), min(hasta, aporte.fecha_hasta)


def _cotizaciones(base_pension, base_salud, base_riesgos, base_caja, tarifas, solidaridad=0, subsistencia=0):
    """Las cotizaciones de una línea, ya aproximadas a la centena."""
    pension = redondear_cien(base_pension * tarifas['pension'] / 100)
    solidaridad = redondear_cien(solidaridad)
    subsistencia = redondear_cien(subsistencia)
    salud = redondear_cien(base_salud * tarifas['salud'] / 100)
    riesgos = redondear_cien(base_riesgos * tarifas['riesgos'] / 100)
    caja = redondear_cien(base_caja * tarifas['caja'] / 100)
    return {
        'cotizacion_pension': pension,
        'cotizacion_solidaridad_solidaridad': solidaridad,
        'cotizacion_solidaridad_subsistencia': subsistencia,
        'cotizacion_voluntario_pension_afiliado': Decimal('0'),
        'cotizacion_voluntario_pension_aportante': Decimal('0'),
        'cotizacion_salud': salud,
        'cotizacion_riesgos': riesgos,
        'cotizacion_caja': caja,
        'cotizacion_sena': Decimal('0'),
        'cotizacion_icbf': Decimal('0'),
        'cotizacion_total': pension + solidaridad + subsistencia + salud + riesgos + caja,
    }


def _liquidar_contrato(aporte, aporte_contrato, filas, configuracion):
    """Las líneas de un contrato y la base de cotización que salió de su nómina."""
    salario_minimo_dia = configuracion.hum_salario_minimo / 30
    salario_dia = aporte_contrato.salario / 30
    tarifa_riesgos = aporte_contrato.riesgo.porcentaje if aporte_contrato.riesgo else Decimal('0')
    comunes = {
        'aporte_contrato': aporte_contrato,
        'ingreso': aporte_contrato.ingreso,
        'retiro': aporte_contrato.retiro,
        'salario_integral': aporte_contrato.contrato.salario_integral,
    }
    lineas = []
    base_nomina = Decimal('0')
    base_sin_novedad = Decimal('0')
    dias_novedad_contrato = 0

    for fila in filas:
        base = fila['base_cotizacion'] or Decimal('0')
        base_nomina += base
        if not fila['novedad_id']:
            base_sin_novedad += base
            continue

        tipo = fila['novedad__novedad_tipo_id']
        dias = int(fila['dias'] or 0)
        dias_novedad_contrato += dias
        tarifas = {'pension': TARIFA_PENSION, 'salud': TARIFA_SALUD, 'riesgos': tarifa_riesgos, 'caja': TARIFA_CAJA}
        marcas = {}
        desde, hasta = _recortar(fila['novedad__fecha_desde'], fila['novedad__fecha_hasta'], aporte)

        # La base de una novedad no puede quedar por debajo del mínimo (incapacidades)
        # ni del salario (licencia no remunerada) por día.
        if dias:
            if tipo in (NOVEDAD_INCAPACIDAD_GENERAL, NOVEDAD_INCAPACIDAD_LABORAL) and base / dias < salario_minimo_dia:
                base = Decimal(math.ceil(salario_minimo_dia * dias))
            if tipo == NOVEDAD_LICENCIA_NO_REMUNERADA and base / dias < salario_dia:
                base = Decimal(math.ceil(salario_dia * dias))

        if tipo == NOVEDAD_INCAPACIDAD_GENERAL:
            tarifas.update(riesgos=0, caja=0)
            marcas.update(incapacidad_general=True,
                          fecha_inicio_incapacidad_general=desde, fecha_fin_incapacidad_general=hasta)
        elif tipo == NOVEDAD_INCAPACIDAD_LABORAL:
            tarifas.update(riesgos=0, caja=0)
            marcas.update(dias_incapacidad_laboral=dias,
                          fecha_inicio_incapacidad_laboral=desde, fecha_fin_incapacidad_laboral=hasta)
        elif tipo == NOVEDAD_LICENCIA_MATERNIDAD:
            tarifas.update(riesgos=0, caja=0)
            marcas.update(licencia_maternidad=True,
                          fecha_inicio_licencia_maternidad=desde, fecha_fin_licencia_maternidad=hasta)
        elif tipo in NOVEDADES_LICENCIA_REMUNERADA:
            # Comparte casilla con vacaciones en la PILA (VAC-LR).
            tarifas.update(riesgos=0)
            marcas.update(licencia_remunerada=True, fecha_inicio_vacaciones=desde, fecha_fin_vacaciones=hasta)
        elif tipo == NOVEDAD_LICENCIA_NO_REMUNERADA:
            tarifas.update(riesgos=0, caja=0, salud=0)
            # Si no se le descontó pensión al empleado en la nómina, solo cotiza el empleador.
            if configuracion.hum_licencia_no_remunerada_afecta_pension:
                tarifas['pension'] = TARIFA_PENSION_EMPLEADOR
            marcas.update(suspension_temporal_contrato=True,
                          fecha_inicio_suspension_temporal_contrato=desde,
                          fecha_fin_suspension_temporal_contrato=hasta)
        elif tipo == NOVEDAD_VACACIONES:
            tarifas.update(riesgos=0)
            marcas.update(vacaciones=True, fecha_inicio_vacaciones=desde, fecha_fin_vacaciones=hasta)

        lineas.append(HumAporteDetalle(
            **comunes,
            **marcas,
            horas=dias * HORAS_DIA,
            dias_pension=dias, dias_salud=dias, dias_riesgos=dias, dias_caja=dias,
            base_cotizacion_pension=base, base_cotizacion_salud=base,
            base_cotizacion_riesgos=base, base_cotizacion_caja=base,
            tarifa_pension=tarifas['pension'], tarifa_salud=tarifas['salud'],
            tarifa_riesgos=tarifas['riesgos'], tarifa_caja=tarifas['caja'],
            **_cotizaciones(base, base, base, base, tarifas),
        ))

    # Los días que no fueron novedad.
    dias = aporte_contrato.dias - dias_novedad_contrato
    if dias > 0:
        base = max(base_sin_novedad, configuracion.hum_salario_minimo / 30 * dias)
        base_pension = base_caja = base
        tarifas = {'pension': TARIFA_PENSION, 'salud': TARIFA_SALUD, 'riesgos': tarifa_riesgos, 'caja': TARIFA_CAJA}
        tipo_cotizante = aporte_contrato.contrato.tipo_cotizante
        if tipo_cotizante is not None and tipo_cotizante.codigo in TIPOS_COTIZANTE_SIN_PENSION:
            base_pension = base_caja = Decimal('0')
            tarifas.update(pension=0, caja=0, salud=TARIFA_SALUD_SIN_PENSION)

        solidaridad = subsistencia = Decimal('0')
        salario_minimo = configuracion.hum_salario_minimo
        if base_pension >= salario_minimo * 4:
            porcentaje = porcentaje_fondo_solidaridad(salario_minimo, base_pension)
            solidaridad = base_pension * FONDO_SUBCUENTA_SOLIDARIDAD / 100
            subsistencia = base_pension * (porcentaje - FONDO_SUBCUENTA_SOLIDARIDAD) / 100

        lineas.append(HumAporteDetalle(
            **comunes,
            # El IBC supera el salario de los días por pagos variables (extras, recargos, comisiones).
            variacion_transitoria_salario=base > math.ceil(salario_dia * dias),
            fecha_ingreso=aporte_contrato.contrato.fecha_desde if aporte_contrato.ingreso else None,
            fecha_retiro=aporte_contrato.contrato.fecha_hasta if aporte_contrato.retiro else None,
            horas=dias * HORAS_DIA,
            dias_pension=dias, dias_salud=dias, dias_riesgos=dias, dias_caja=dias,
            base_cotizacion_pension=base_pension, base_cotizacion_salud=base,
            base_cotizacion_riesgos=base, base_cotizacion_caja=base_caja,
            tarifa_pension=tarifas['pension'], tarifa_salud=tarifas['salud'],
            tarifa_riesgos=tarifas['riesgos'], tarifa_caja=tarifas['caja'],
            **_cotizaciones(base_pension, base, base, base_caja, tarifas, solidaridad, subsistencia),
        ))
    return lineas, base_nomina


def _totalizar(aporte, aporte_contratos, detalles):
    """Suma los detalles en cada contrato y los contratos en el aporte."""
    por_contrato = defaultdict(lambda: defaultdict(Decimal))
    for detalle in detalles:
        for campo in _COTIZACIONES:
            por_contrato[detalle.aporte_contrato_id][campo] += getattr(detalle, campo)

    for campo in _COTIZACIONES + (
        'cotizacion_pension_total', 'cotizacion_pension_empresa', 'cotizacion_pension_empleado',
        'cotizacion_salud_empresa', 'cotizacion_salud_empleado',
    ):
        setattr(aporte, campo, Decimal('0'))

    for aporte_contrato in aporte_contratos:
        sumas = por_contrato[aporte_contrato.id]
        for campo in _COTIZACIONES:
            setattr(aporte_contrato, campo, sumas[campo])
        aporte_contrato.cotizacion_pension_total = (
            sumas['cotizacion_pension'] + sumas['cotizacion_solidaridad_solidaridad']
            + sumas['cotizacion_solidaridad_subsistencia'] + sumas['cotizacion_voluntario_pension_afiliado']
            + sumas['cotizacion_voluntario_pension_aportante']
        )
        # Lo que pone la empresa es lo que no se le descontó al empleado en la nómina.
        aporte_contrato.cotizacion_pension_empresa = (
            aporte_contrato.cotizacion_pension_total - aporte_contrato.cotizacion_pension_empleado
        )
        aporte_contrato.cotizacion_salud_empresa = sumas['cotizacion_salud'] - aporte_contrato.cotizacion_salud_empleado
        for campo in _COTIZACIONES + (
            'cotizacion_pension_total', 'cotizacion_pension_empresa', 'cotizacion_pension_empleado',
            'cotizacion_salud_empresa', 'cotizacion_salud_empleado',
        ):
            setattr(aporte, campo, getattr(aporte, campo) + getattr(aporte_contrato, campo))
    HumAporteContrato.objects.bulk_update(
        aporte_contratos,
        list(_COTIZACIONES) + ['cotizacion_pension_total', 'cotizacion_pension_empresa', 'cotizacion_salud_empresa'],
    )


def _crear_entidades(aporte):
    """
    Lo que se le debe a cada entidad, desde los detalles: pensión (con el fondo de
    solidaridad), salud y caja por la entidad de cada contrato; riesgos, SENA e
    ICBF por las del aporte, que siempre aparecen aunque sea en cero.
    """
    HumAporteEntidad.objects.filter(aporte=aporte).delete()
    totales = {}
    for tipo, entidad_id in (('RIESGO', aporte.entidad_riesgo_id), ('SENA', aporte.entidad_sena_id),
                             ('ICBF', aporte.entidad_icbf_id)):
        if entidad_id is not None:
            totales[(tipo, entidad_id)] = Decimal('0')

    detalles = HumAporteDetalle.objects.filter(aporte_contrato__aporte=aporte).select_related('aporte_contrato')
    for detalle in detalles:
        contrato = detalle.aporte_contrato
        for tipo, entidad_id, valor in (
            ('PENSION', contrato.entidad_pension_id, detalle.cotizacion_pension
             + detalle.cotizacion_solidaridad_solidaridad + detalle.cotizacion_solidaridad_subsistencia),
            ('SALUD', contrato.entidad_salud_id, detalle.cotizacion_salud),
            ('CAJA', contrato.entidad_caja_id, detalle.cotizacion_caja),
            ('RIESGO', aporte.entidad_riesgo_id, detalle.cotizacion_riesgos),
            ('SENA', aporte.entidad_sena_id, detalle.cotizacion_sena),
            ('ICBF', aporte.entidad_icbf_id, detalle.cotizacion_icbf),
        ):
            if entidad_id is not None:
                totales[(tipo, entidad_id)] = totales.get((tipo, entidad_id), Decimal('0')) + valor

    HumAporteEntidad.objects.bulk_create(
        HumAporteEntidad(aporte=aporte, tipo=tipo, entidad_id=entidad_id, cotizacion=total)
        for (tipo, entidad_id), total in sorted(totales.items(), key=lambda par: TIPOS_ENTIDAD.index(par[0][0]))
    )


def recalcular_entidades(aporte):
    """Vuelve a armar lo que se le debe a cada entidad desde los detalles del aporte."""
    with transaction.atomic():
        aporte = _bloquear(aporte)
        if aporte.estado_aprobado or not aporte.estado_generado:
            raise AporteError('El aporte debe estar generado y sin aprobar.')
        _crear_entidades(aporte)
    return aporte


def desgenerar_aporte(aporte):
    """Borra los detalles y las entidades del aporte y deja todos sus totales en cero."""
    with transaction.atomic():
        aporte = _bloquear(aporte)
        if aporte.estado_aprobado:
            raise AporteError('El aporte está aprobado.')
        if not aporte.estado_generado:
            raise AporteError('El aporte no está generado.')

        HumAporteDetalle.objects.filter(aporte_contrato__aporte=aporte).delete()
        HumAporteEntidad.objects.filter(aporte=aporte).delete()
        en_cero = {campo: 0 for campo in _COTIZACIONES + (
            'cotizacion_pension_total', 'cotizacion_pension_empresa', 'cotizacion_salud_empresa',
        )}
        HumAporteContrato.objects.filter(aporte=aporte).update(**en_cero)

        for campo in en_cero:
            setattr(aporte, campo, 0)
        aporte.cotizacion_pension_empleado = 0
        aporte.cotizacion_salud_empleado = 0
        aporte.base_cotizacion = 0
        aporte.lineas = 0
        aporte.estado_generado = False
        aporte.save()
    return aporte


# ----------------------------------------------------------- aprobar ----

# Por cada tipo de entidad: el campo de `HumAporteContrato` que dice a cuál se le
# paga, lo que suma el contrato y la parte que pone la empresa.
_DOCUMENTOS_ENTIDAD = (
    ('PENSION', 'entidad_pension', 'cotizacion_pension_total', 'cotizacion_pension_empresa'),
    ('SALUD', 'entidad_salud', 'cotizacion_salud', 'cotizacion_salud_empresa'),
    ('CAJA', 'entidad_caja', 'cotizacion_caja', 'cotizacion_caja'),
    ('RIESGO', 'entidad_riesgo', 'cotizacion_riesgos', 'cotizacion_riesgos'),
    ('SENA', 'entidad_sena', 'cotizacion_sena', 'cotizacion_sena'),
    ('ICBF', 'entidad_icbf', 'cotizacion_icbf', 'cotizacion_icbf'),
)


def aprobar_aporte(aporte):
    """
    Crea y aprueba un documento de seguridad social (tipo 22) por cada entidad con
    algo por pagar, con una línea por contrato. El consecutivo y la cartera los
    pone `general.servicios.documento.aprobar`.
    """
    with transaction.atomic():
        aporte = _bloquear(aporte)
        if aporte.estado_aprobado:
            raise AporteError('El aporte ya está aprobado.')
        if not aporte.estado_generado:
            raise AporteError('El aporte no está generado.')

        aporte_contratos = list(
            HumAporteContrato.objects.filter(aporte=aporte)
            .select_related(*(campo for _, campo, _, _ in _DOCUMENTOS_ENTIDAD), 'contrato')
            .order_by('id')
        )
        # El documento va a nombre del contacto de la entidad, que se ubica por su
        # identificación. Sin él no hay a quién cargarle la cuenta por pagar.
        entidades = {}
        for tipo, campo, total, _ in _DOCUMENTOS_ENTIDAD:
            for aporte_contrato in aporte_contratos:
                entidad = getattr(aporte_contrato, campo)
                if entidad is not None and getattr(aporte_contrato, total) > 0:
                    entidades[(tipo, entidad.id)] = entidad
        contactos = dict(
            GenContacto.objects.filter(
                numero_identificacion__in={entidad.numero_identificacion for entidad in entidades.values()},
            ).order_by('-id').values_list('numero_identificacion', 'id')
        )
        errores = [
            {'tipo': tipo, 'entidad': entidad.nombre, 'mensaje': (
                f'La entidad {entidad.nombre} ({entidad.numero_identificacion}) no existe en contactos.'
            )}
            for (tipo, _), entidad in entidades.items()
            if entidad.numero_identificacion not in contactos
        ]
        if errores:
            raise AporteError('Hay entidades que no están creadas como contacto.', errores)

        documento_ids = []
        for tipo, campo, total, empresa in _DOCUMENTOS_ENTIDAD:
            por_entidad = defaultdict(list)
            for aporte_contrato in aporte_contratos:
                entidad = getattr(aporte_contrato, campo)
                if entidad is not None and getattr(aporte_contrato, total) > 0:
                    por_entidad[entidad].append(aporte_contrato)

            for entidad, contratos in por_entidad.items():
                documento = GenDocumento.objects.create(
                    aporte=aporte,
                    documento_tipo_id=DOCUMENTO_TIPO_SEGURIDAD_SOCIAL,
                    contacto_id=contactos[entidad.numero_identificacion],
                    orden_compra=tipo,
                    fecha=aporte.fecha_desde,
                    fecha_vence=aporte.fecha_desde,
                    fecha_contable=aporte.fecha_desde,
                    fecha_hasta=aporte.fecha_hasta,
                    subtotal=sum(getattr(ac, empresa) for ac in contratos),
                    total=sum(getattr(ac, total) for ac in contratos),
                )
                GenDocumentoDetalle.objects.bulk_create(
                    GenDocumentoDetalle(
                        documento=documento,
                        tipo_registro='S',
                        detalle=tipo,
                        contacto_id=ac.contrato.contacto_id,
                        contrato_id=ac.contrato_id,
                        precio=getattr(ac, empresa),
                        pago=getattr(ac, total),
                    )
                    for ac in contratos
                )
                documento_ids.append(documento.id)

        try:
            for documento_id in documento_ids:
                servicio_documento.aprobar(documento_id)
        except ValidationError as e:
            raise AporteError(_mensaje(e))

        aporte.estado_aprobado = True
        aporte.save(update_fields=['estado_aprobado'])
    return aporte


def desaprobar_aporte(aporte):
    """
    Borra los documentos de seguridad social del aporte. No se puede si alguno
    ya tiene un egreso o está contabilizado.
    """
    with transaction.atomic():
        aporte = _bloquear(aporte)
        if not aporte.estado_aprobado:
            raise AporteError('El aporte no está aprobado.')

        documentos = list(GenDocumento.objects.filter(aporte=aporte).select_for_update())
        for documento in documentos:
            if documento.afectado > 0:
                raise AporteError(f'El documento {documento.numero} ya tiene un egreso: no se puede desaprobar el aporte.')
            if documento.estado_contabilizado:
                raise AporteError(f'El documento {documento.numero} está contabilizado: no se puede desaprobar el aporte.')

        GenDocumentoDetalle.objects.filter(documento__in=documentos).delete()
        GenDocumento.objects.filter(id__in=[documento.id for documento in documentos]).delete()

        aporte.estado_aprobado = False
        aporte.save(update_fields=['estado_aprobado'])
    return aporte


def _mensaje(error):
    """El texto de un `ValidationError` de DRF, que puede venir como lista o dict."""
    detalle = error.detail
    if isinstance(detalle, list) and detalle:
        return str(detalle[0])
    if isinstance(detalle, dict) and detalle:
        primero = next(iter(detalle.values()))
        return str(primero[0] if isinstance(primero, list) and primero else primero)
    return str(detalle)
