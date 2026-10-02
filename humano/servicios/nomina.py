"""
El cálculo de un documento de nómina a partir de un `HumProgramacionDetalle`.

`programacion.generar_programacion` arma el contexto una vez para toda la
programación (`ContextoNomina`) y llama a `liquidar_detalle` por cada detalle.
Acá no se guarda nada salvo el documento y sus líneas: el estado de la
programación lo maneja quien llama.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from general.models import GenContacto, GenDocumento, GenDocumentoDetalle
from humano.models import HumAdicional, HumConcepto, HumConceptoNomina, HumCredito, HumNovedad

PAGO_TIPO_NOMINA = 1
PAGO_TIPO_PRIMA = 2
PAGO_TIPO_CESANTIA = 3
PAGO_TIPO_INTERES = 4

DOCUMENTO_TIPO_POR_PAGO_TIPO = {
    PAGO_TIPO_NOMINA: 14,    # NOMINA
    PAGO_TIPO_PRIMA: 20,     # PRIMA
    PAGO_TIPO_CESANTIA: 21,  # CESANTIA
    PAGO_TIPO_INTERES: 33,   # INTERES CESANTIA
}

# `HumConceptoNomina`: qué concepto paga cada cosa. El id es fijo (catálogo).
CONCEPTO_NOMINA_AUXILIO_TRANSPORTE = 12
CONCEPTO_NOMINA_PRIMA = 13
CONCEPTO_NOMINA_CESANTIA = 14
CONCEPTO_NOMINA_INTERES = 15

# Las horas del detalle y el `HumConceptoNomina` con el que se pagan.
HORAS_CONCEPTO_NOMINA = (
    ('diurna', 1),
    ('nocturna', 2),
    ('festiva_diurna', 3),
    ('festiva_nocturna', 4),
    ('extra_diurna', 5),
    ('extra_nocturna', 6),
    ('extra_festiva_diurna', 7),
    ('extra_festiva_nocturna', 8),
    ('recargo_nocturno', 9),
    ('recargo_festivo_diurno', 10),
    ('recargo_festivo_nocturno', 11),
)

NOVEDAD_TIPOS_INCAPACIDAD = (1, 2)
NOVEDAD_TIPO_LICENCIA_MATERNIDAD = 3
NOVEDAD_TIPOS_LICENCIA_EMPRESA = (4, 5)  # luto y remunerada
NOVEDAD_TIPO_LICENCIA_NO_REMUNERADA = 6
NOVEDAD_TIPOS_LICENCIA = (3, 4, 5, 6)
NOVEDAD_TIPO_VACACION = 7

# Licencia no remunerada: no paga, pero sí cotiza sobre lo que habría ganado.
CONCEPTO_LICENCIA_NO_REMUNERADA = 28
CONCEPTO_FONDO_SOLIDARIDAD = 20
TIEMPO_MEDIO = 2
# Aprendiz en etapa lectiva: no se le descuenta salud ni pensión.
TIPO_COTIZANTE_APRENDIZ_LECTIVO = '12'

# Fracciones de la base que se provisionan en cada documento de nómina.
PROVISION_CESANTIA = Decimal('0.0833')
PROVISION_INTERES = Decimal('0.12')
PROVISION_PRIMA = Decimal('0.0833')
PROVISION_VACACION = Decimal('0.0417')


class NominaError(ValueError):
    """Falta algo para liquidar un detalle; va como `detail`."""

    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


def redondear(valor):
    """A pesos enteros, con la mitad hacia arriba."""
    return Decimal(valor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def porcentaje_fondo_solidaridad(salario_minimo, base_cotizacion):
    """El porcentaje del fondo de solidaridad pensional según los salarios mínimos de la base."""
    salarios = base_cotizacion / salario_minimo
    if salarios >= 20:
        return Decimal('2')
    for desde, porcentaje in ((19, '1.8'), (18, '1.6'), (17, '1.4'), (16, '1.2'), (4, '1')):
        if salarios >= desde:
            return Decimal(porcentaje)
    return Decimal('0')


@dataclass
class _Acumulado:
    """Lo que van sumando las líneas del documento."""
    devengado: Decimal = Decimal('0')
    deduccion: Decimal = Decimal('0')
    base_cotizacion: Decimal = Decimal('0')
    base_prestacion: Decimal = Decimal('0')
    base_prestacion_vacacion: Decimal = Decimal('0')
    base_licencia: Decimal = Decimal('0')
    lineas: list = field(default_factory=list)


@dataclass
class ContextoNomina:
    """Todo lo que se consulta una sola vez para liquidar una programación entera."""
    programacion: object
    configuracion: object
    conceptos_nomina: dict
    concepto_fondo: object
    novedades: dict
    adicionales: dict
    creditos: dict
    contactos_entidad: dict

    @classmethod
    def cargar(cls, programacion, configuracion, contratos):
        contrato_ids = [contrato.id for contrato in contratos]

        novedades = defaultdict(list)
        for novedad in HumNovedad.objects.filter(
            contrato_id__in=contrato_ids,
            fecha_desde__lte=programacion.fecha_hasta,
            fecha_hasta__gte=programacion.fecha_desde,
        ).select_related('novedad_tipo__concepto', 'novedad_tipo__concepto2').order_by('fecha_desde', 'id'):
            novedades[novedad.contrato_id].append(novedad)

        adicionales = defaultdict(list)
        filtro_adicional = Q(programacion=programacion)
        if programacion.pago_tipo_id == PAGO_TIPO_NOMINA:
            filtro_adicional |= Q(permanente=True)
        for adicional in HumAdicional.objects.filter(
            filtro_adicional, contrato_id__in=contrato_ids, inactivo=False,
        ).select_related('concepto').order_by('id'):
            adicionales[adicional.contrato_id].append(adicional)

        creditos = defaultdict(list)
        filtro_credito = {}
        if programacion.pago_tipo_id == PAGO_TIPO_PRIMA:
            filtro_credito['aplica_prima'] = True
        elif programacion.pago_tipo_id == PAGO_TIPO_CESANTIA:
            filtro_credito['aplica_cesantia'] = True
        for credito in HumCredito.objects.filter(
            contrato_id__in=contrato_ids, inactivo=False, pagado=False, saldo__gt=0, **filtro_credito,
        ).select_related('concepto').order_by('id'):
            creditos[credito.contrato_id].append(credito)

        # Salud, pensión y fondo se le deben a la entidad: la línea va a nombre de
        # su contacto, que se ubica por número de identificación.
        identificaciones = {
            entidad.numero_identificacion
            for contrato in contratos
            for entidad in (contrato.entidad_salud, contrato.entidad_pension)
            if entidad is not None
        }
        contactos_entidad = dict(
            GenContacto.objects.filter(numero_identificacion__in=identificaciones)
            .order_by('-id').values_list('numero_identificacion', 'id')
        )

        return cls(
            programacion=programacion,
            configuracion=configuracion,
            conceptos_nomina={
                concepto_nomina.id: concepto_nomina.concepto
                for concepto_nomina in HumConceptoNomina.objects.select_related('concepto')
            },
            concepto_fondo=HumConcepto.objects.filter(pk=CONCEPTO_FONDO_SOLIDARIDAD).first(),
            novedades=novedades,
            adicionales=adicionales,
            creditos=creditos,
            contactos_entidad=contactos_entidad,
        )

    def concepto_nomina(self, concepto_nomina_id):
        concepto = self.conceptos_nomina.get(concepto_nomina_id)
        if concepto is None:
            raise NominaError(f'Falta el concepto de nómina {concepto_nomina_id}.')
        return concepto

    def contacto_entidad(self, entidad):
        return self.contactos_entidad.get(entidad.numero_identificacion) if entidad else None


def liquidar_detalle(contexto, detalle):
    """
    Crea el documento de nómina del detalle con todas sus líneas y deja en el
    detalle `devengado`, `deduccion` y `total` (sin guardarlo).
    """
    programacion = contexto.programacion
    contrato = detalle.contrato
    documento = GenDocumento.objects.create(
        programacion_detalle=detalle,
        documento_tipo_id=DOCUMENTO_TIPO_POR_PAGO_TIPO[programacion.pago_tipo_id],
        fecha=detalle.fecha_hasta,
        fecha_vence=detalle.fecha_hasta,
        fecha_contable=detalle.fecha_hasta,
        fecha_desde=detalle.fecha_desde,
        fecha_hasta=detalle.fecha_hasta,
        contrato=contrato,
        contacto_id=contrato.contacto_id,
        salario=detalle.salario,
        dias=detalle.dias,
    )
    acumulado = _Acumulado()

    def linea(concepto, pago, **campos):
        _agregar_linea(acumulado, documento, contrato.contacto_id, concepto, pago, **campos)

    configuracion = contexto.configuracion
    valor_hora = detalle.salario / 30 / configuracion.hum_factor

    if programacion.pago_tipo_id == PAGO_TIPO_NOMINA:
        _horas(contexto, detalle, valor_hora, linea)
        _novedades(contexto, detalle, valor_hora, linea)
        _auxilio_transporte(contexto, detalle, linea)
    elif programacion.pago_tipo_id == PAGO_TIPO_PRIMA and programacion.pago_prima:
        _prestacion(detalle, detalle.prima_propuesto, contexto.concepto_nomina(CONCEPTO_NOMINA_PRIMA), linea)
    elif programacion.pago_tipo_id == PAGO_TIPO_CESANTIA and programacion.pago_cesantia:
        _prestacion(detalle, detalle.cesantia_propuesto, contexto.concepto_nomina(CONCEPTO_NOMINA_CESANTIA), linea)
    elif programacion.pago_tipo_id == PAGO_TIPO_INTERES and programacion.pago_interes:
        _interes(contexto, detalle, linea)

    if detalle.adicional:
        _adicionales(contexto, detalle, linea)
    if detalle.descuento_credito:
        _creditos(contexto, detalle, linea)
    _seguridad_social(contexto, detalle, acumulado, linea)

    GenDocumentoDetalle.objects.bulk_create(acumulado.lineas)

    total = acumulado.devengado - acumulado.deduccion
    provision_cesantia = acumulado.base_prestacion * PROVISION_CESANTIA
    documento.provision_cesantia = redondear(provision_cesantia)
    documento.provision_interes = redondear(provision_cesantia * PROVISION_INTERES)
    documento.provision_prima = redondear(acumulado.base_prestacion * PROVISION_PRIMA)
    documento.provision_vacacion = redondear(acumulado.base_prestacion_vacacion * PROVISION_VACACION)
    documento.base_cotizacion = acumulado.base_cotizacion
    documento.base_prestacion = acumulado.base_prestacion
    documento.base_prestacion_vacacion = acumulado.base_prestacion_vacacion
    documento.devengado = acumulado.devengado
    documento.deduccion = acumulado.deduccion
    documento.total = total
    documento.save(update_fields=[
        'provision_cesantia', 'provision_interes', 'provision_prima', 'provision_vacacion',
        'base_cotizacion', 'base_prestacion', 'base_prestacion_vacacion',
        'devengado', 'deduccion', 'total',
    ])

    detalle.devengado = acumulado.devengado
    detalle.deduccion = acumulado.deduccion
    detalle.total = total
    return documento


def _agregar_linea(acumulado, documento, contacto_empleado_id, concepto, pago, **campos):
    """
    Arma la línea y la suma al acumulado según el concepto: devengado o deducción
    por su `operacion`, y las bases en las que entra.
    """
    if concepto is None:
        raise NominaError('Hay un concepto de nómina sin configurar.')
    pago = Decimal(pago)
    # Por defecto la línea es del empleado; salud, pensión y fondo la ponen a nombre de la entidad.
    campos.setdefault('contacto_id', contacto_empleado_id)
    detalle = GenDocumentoDetalle(
        documento=documento,
        tipo_registro='N',
        concepto=concepto,
        pago=pago,
        operacion=concepto.operacion,
        pago_operado=pago * concepto.operacion,
        **campos,
    )
    if concepto.operacion == 1:
        detalle.devengado = pago
        acumulado.devengado += pago
    elif concepto.operacion == -1:
        detalle.deduccion = pago
        acumulado.deduccion += pago
    if concepto.ingreso_base_cotizacion:
        if concepto.id == CONCEPTO_LICENCIA_NO_REMUNERADA:
            # No paga nada: cotiza sobre las horas que no trabajó al valor de su hora.
            base = redondear(detalle.cantidad * detalle.hora)
            acumulado.base_licencia += base
        else:
            base = pago
        detalle.base_cotizacion = base
        acumulado.base_cotizacion += base
    if concepto.ingreso_base_prestacion:
        detalle.base_prestacion = pago
        acumulado.base_prestacion += pago
    if concepto.ingreso_base_prestacion_vacacion:
        detalle.base_prestacion_vacacion = pago
        acumulado.base_prestacion_vacacion += pago
    acumulado.lineas.append(detalle)


def _horas(contexto, detalle, valor_hora, linea):
    if not detalle.pago_horas:
        return
    for campo, concepto_nomina_id in HORAS_CONCEPTO_NOMINA:
        cantidad = getattr(detalle, campo)
        if cantidad <= 0:
            continue
        concepto = contexto.concepto_nomina(concepto_nomina_id)
        hora = (valor_hora * concepto.porcentaje / 100).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        linea(
            concepto, redondear(hora * cantidad),
            cantidad=cantidad, hora=hora, dias=detalle.dias, porcentaje=concepto.porcentaje,
        )


def _dias_entre(desde, hasta):
    return (hasta - desde).days + 1


def _novedades(contexto, detalle, valor_hora, linea):
    programacion = contexto.programacion
    factor = contexto.configuracion.hum_factor
    for novedad in contexto.novedades.get(detalle.contrato_id, ()):
        tipo = novedad.novedad_tipo_id
        desde = max(novedad.fecha_desde, programacion.fecha_desde)
        hasta = min(novedad.fecha_hasta, programacion.fecha_hasta)
        dias_novedad = _dias_entre(desde, hasta)
        datos_novedad = {'novedad': novedad, 'detalle': novedad.detalle}

        if tipo in NOVEDAD_TIPOS_INCAPACIDAD and detalle.pago_incapacidad:
            # Los primeros días los paga la empresa y el resto la entidad, cada
            # parte con su concepto y su valor hora.
            tramos = (
                (novedad.dias_empresa, novedad.fecha_desde_empresa, novedad.fecha_hasta_empresa,
                 novedad.hora_empresa, novedad.novedad_tipo.concepto),
                (novedad.dias_entidad, novedad.fecha_desde_entidad, novedad.fecha_hasta_entidad,
                 novedad.hora_entidad, novedad.novedad_tipo.concepto2),
            )
            for dias_tramo, tramo_desde, tramo_hasta, hora, concepto in tramos:
                if dias_tramo <= 0 or tramo_desde is None or tramo_hasta is None:
                    continue
                dias = _dias_entre(
                    max(tramo_desde, programacion.fecha_desde), min(tramo_hasta, programacion.fecha_hasta),
                )
                if dias <= 0:
                    continue
                horas = dias * factor
                linea(
                    concepto, redondear(hora * horas),
                    dias=dias, hora=hora, cantidad=horas, porcentaje=concepto.porcentaje if concepto else 0,
                    **datos_novedad,
                )

        elif tipo in NOVEDAD_TIPOS_LICENCIA and detalle.pago_licencia and dias_novedad > 0:
            if tipo == NOVEDAD_TIPO_LICENCIA_MATERNIDAD:
                hora = novedad.hora_entidad
            elif tipo in NOVEDAD_TIPOS_LICENCIA_EMPRESA:
                hora = novedad.hora_empresa
            else:
                hora = valor_hora.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
            horas = dias_novedad * factor
            pago = 0 if tipo == NOVEDAD_TIPO_LICENCIA_NO_REMUNERADA else redondear(hora * horas)
            concepto = novedad.novedad_tipo.concepto
            linea(
                concepto, pago,
                dias=dias_novedad, hora=hora, cantidad=horas, porcentaje=concepto.porcentaje if concepto else 0,
                **datos_novedad,
            )

        elif tipo == NOVEDAD_TIPO_VACACION and detalle.pago_vacacion:
            # En una quincena que termina el 31, las vacaciones que lo cubren pagan
            # ese día aparte: el periodo se cuenta de 15 días pero el 31 también se disfruta.
            dia31 = int(
                programacion.fecha_hasta_periodo.day == 31
                and novedad.fecha_hasta >= programacion.fecha_hasta_periodo
            )
            dias_pago = dias_novedad + dia31
            linea(
                novedad.novedad_tipo.concepto, redondear(dias_pago * novedad.pago_dia_disfrute),
                dias=dias_novedad, **datos_novedad,
            )
            linea(
                novedad.novedad_tipo.concepto2, redondear(dias_pago * novedad.pago_dia_dinero),
                dias=dias_novedad, **datos_novedad,
            )


def _auxilio_transporte(contexto, detalle, linea):
    if not (detalle.pago_auxilio_transporte and detalle.contrato.auxilio_transporte):
        return
    pago = redondear(contexto.configuracion.hum_auxilio_transporte / 30 * detalle.dias_transporte)
    if pago > 0:
        linea(contexto.concepto_nomina(CONCEPTO_NOMINA_AUXILIO_TRANSPORTE), pago, dias=detalle.dias_transporte)


def _prestacion(detalle, propuesto, concepto, linea):
    """Prima o cesantía: salario promedio por días sobre 360, salvo que haya valor propuesto."""
    valor = propuesto if propuesto > 0 else detalle.salario_promedio * detalle.dias / 360
    pago = redondear(valor)
    if pago > 0:
        linea(concepto, pago, dias=detalle.dias)


def _interes(contexto, detalle, linea):
    """12 % anual de la cesantía, proporcional a los días."""
    if detalle.interes_propuesto > 0:
        valor = detalle.interes_propuesto
    else:
        cesantia = detalle.salario_promedio * detalle.dias / 360
        valor = cesantia * (detalle.dias * 12 / 360) / 100
    pago = redondear(valor)
    if pago > 0:
        linea(contexto.concepto_nomina(CONCEPTO_NOMINA_INTERES), pago, dias=detalle.dias)


def _adicionales(contexto, detalle, linea):
    programacion = contexto.programacion
    for adicional in contexto.adicionales.get(detalle.contrato_id, ()):
        valor = adicional.valor
        if adicional.aplica_dia_laborado:
            # El valor es por el periodo completo: se paga en proporción a los días laborados.
            valor = adicional.valor / programacion.dias * detalle.dias if programacion.dias else Decimal('0')
        linea(adicional.concepto, redondear(valor), detalle=adicional.detalle)


def _creditos(contexto, detalle, linea):
    for credito in contexto.creditos.get(detalle.contrato_id, ()):
        linea(credito.concepto, redondear(min(credito.cuota, credito.saldo)), credito=credito)


def _seguridad_social(contexto, detalle, acumulado, linea):
    """Salud, pensión y fondo de solidaridad, sobre la base de cotización ya acumulada."""
    contrato = detalle.contrato
    configuracion = contexto.configuracion
    salario_minimo = configuracion.hum_salario_minimo
    base_salario_minimo = salario_minimo / 30 * detalle.dias
    tipo_cotizante = contrato.tipo_cotizante
    cotiza = tipo_cotizante is None or tipo_cotizante.codigo != TIPO_COTIZANTE_APRENDIZ_LECTIVO

    def base_minima(base):
        # Medio tiempo cotiza como mínimo sobre el salario mínimo de los días.
        if contrato.tiempo_id == TIEMPO_MEDIO and base < base_salario_minimo:
            return base_salario_minimo
        return base

    salud = contrato.salud
    if detalle.descuento_salud and cotiza and salud and salud.porcentaje_empleado > 0:
        # La licencia no remunerada cotiza pensión pero no salud.
        base = base_minima(acumulado.base_cotizacion - acumulado.base_licencia)
        if base > 0:
            linea(
                salud.concepto, redondear(base * salud.porcentaje_empleado / 100),
                porcentaje=salud.porcentaje_empleado,
                contacto_id=contexto.contacto_entidad(contrato.entidad_salud),
            )

    pension = contrato.pension
    if (
        detalle.descuento_pension and cotiza and pension and pension.porcentaje_empleado > 0
        and acumulado.base_cotizacion > 0
    ):
        base = base_minima(acumulado.base_cotizacion)
        linea(
            pension.concepto, redondear(base * pension.porcentaje_empleado / 100),
            porcentaje=pension.porcentaje_empleado,
            contacto_id=contexto.contacto_entidad(contrato.entidad_pension),
        )

    if detalle.descuento_fondo_solidaridad and pension:
        # Se calcula sobre todo el mes: lo de esta nómina más lo ya liquidado, y se
        # descuenta lo que ya se dedujo de fondo en el mes.
        base = acumulado.base_cotizacion + detalle.base_cotizacion_acumulado
        if base >= salario_minimo * 4:
            porcentaje = porcentaje_fondo_solidaridad(salario_minimo, base)
            base = min(base, redondear(salario_minimo * 25))
            pago = redondear(base * porcentaje / 100) - redondear(detalle.deduccion_fondo_pension_acumulado)
            if porcentaje > 0 and pago > 0:
                linea(
                    contexto.concepto_fondo, pago, porcentaje=porcentaje,
                    contacto_id=contexto.contacto_entidad(contrato.entidad_pension),
                )
