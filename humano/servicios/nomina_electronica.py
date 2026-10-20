"""
Nómina electrónica: el documento soporte de pago de nómina que se reporta a la
DIAN por rededoc. Portado de `generar_nomina_electronica` y `emitir` de itrio.

**Generar** junta, por empleado y mes, las nóminas aprobadas (clase 701:
nómina, prima, cesantía, interés y liquidación) en un documento de tipo NOMINA ELECTRONICA.
Cada nómina queda como una línea y apunta a su electrónica por
`documento_referencia`; de ahí la saca el envío y por ahí se sabe que ya está
reportada. Se genera aprobado, como en itrio: es un resumen de nóminas ya
aprobadas, no algo que alguien vaya a editar.

**Desgenerar** borra las electrónicas del mes que todavía no se enviaron y
libera sus nóminas, para corregir y volver a generar.

**Armar** el envío convierte las líneas de las nóminas en los conceptos de
rededoc (`NominaConcepto` en nobelio) por el tipo de concepto, como itrio. Los
conceptos que la DIAN pide una sola vez (básico, prima, cesantías, salud,
pensión…) se suman, porque rededoc solo toma la primera fila de cada uno.
"""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from general.models import GenConfiguracion, GenDocumento, GenDocumentoDetalle, GenDocumentoTipo
from general.servicios import documento as servicio_documento
from general.servicios.documento import DOCUMENTO_CLASE_NOMINA
from utilidades.fechas import dias_prestacionales

DOCUMENTO_TIPO_NOMINA_ELECTRONICA = 15

CERO = Decimal('0')

# ------------------------------------------------------ catálogos rededoc ----
#
# Los catálogos viajan con el id de rededoc. Los de torio no coinciden, así que
# se cruzan por código (tipo de trabajador, subtipo) o por id (contrato, periodo).

# Código PILA del tipo de cotizante → id de `TipoTrabajador` en rededoc. Los
# que no están (03 independiente, 15 desempleado, …) no se reportan en nómina.
TIPO_TRABAJADOR = {
    '01': 1, '02': 2, '04': 3, '12': 4, '18': 5, '19': 6, '21': 7, '22': 8,
    '23': 9, '30': 10, '31': 11, '47': 12, '51': 13, '54': 14, '56': 15, '58': 16,
}
# Código del subtipo de cotizante → id de `SubTipoTrabajador`. La DIAN solo
# distingue al pensionado por vejez activo (01); los demás subtipos de PILA
# salen como «No aplica».
SUBTIPO_PENSIONADO = '01'
SUBTIPO_TRABAJADOR = {'00': 1, SUBTIPO_PENSIONADO: 2}
# `HumContratoTipo` → `TipoContrato`: 1 indefinido, 2 fijo, 3 obra, 4 aprendiz,
# 5 práctica; en rededoc 1 es término fijo y 2 indefinido.
TIPO_CONTRATO = {1: 2, 2: 1, 3: 3, 4: 4, 5: 5}
# `HumPeriodo` (1 quincenal, 2 mensual) → `PeriodoNomina` (4 quincenal, 5 mensual).
PERIODO_NOMINA = {1: 4, 2: 5}
FORMA_PAGO_CONTADO = 1
MEDIO_PAGO_EFECTIVO = 10
MEDIO_PAGO_CONSIGNACION = 42
MONEDA_COP = 35
# `GenCuentaBancoClase` → `Empleado.TipoCuenta`.
TIPO_CUENTA = {1: 'ahorros', 2: 'corriente'}
PREFIJO = 'NE'
TIPO_XML_NOMINA = '102'

# ------------------------------------------------------------- conceptos ----
#
# `HumConceptoTipo` → concepto de rededoc. Lo que no esté acá corta el envío: un
# pago que no se reporta descuadra el total que la DIAN compara.

DEVENGADO = 'devengado'
DEDUCCION = 'deduccion'

# Un solo concepto por documento: se suman cantidad y valor.
SUMADOS = {
    1: (DEVENGADO, 'basico'),
    7: (DEVENGADO, 'auxilio_transporte'),
    20: (DEVENGADO, 'prima'),
    21: (DEVENGADO, 'prima'),
    22: (DEVENGADO, 'cesantias'),
    23: (DEVENGADO, 'cesantias'),
    24: (DEVENGADO, 'intereses_cesantias'),
    25: (DEVENGADO, 'intereses_cesantias'),
    5: (DEDUCCION, 'salud'),
    6: (DEDUCCION, 'fondo_pension'),
    9: (DEDUCCION, 'fondo_sp'),
    8: (DEDUCCION, 'deuda'),
    10: (DEDUCCION, 'retencion_fuente'),
}
# Una fila por línea, con las fechas de su novedad.
CON_FECHAS = {
    12: 'incapacidad',
    13: 'incapacidad',
    14: 'licencia_mp',
    15: 'licencia_remunerada',
    16: 'licencia_remunerada',
    17: 'licencia_no_remunerada',
    18: 'vacaciones_comunes',
}
TIPO_INCAPACIDAD = {12: '1', 13: '3'}  # común, laboral
CONCEPTO_TIPO_EXTRAS = 2
CONCEPTO_TIPO_VACACIONES_DINERO = 19
CONCEPTO_TIPO_SALARIAL = 3
CONCEPTO_TIPO_NO_SALARIAL = 4
CONCEPTO_TIPO_DESCUENTO = 11
CONCEPTO_COMISION = 38
# Intereses de cesantías: la DIAN pide su porcentaje, que es el legal.
PORCENTAJE_INTERESES = Decimal('12')

# Horas extras y recargos por `HumConcepto`, con el recargo que exige la DIAN
# (el porcentaje de torio incluye la hora ordinaria: 125 % es un recargo de 25).
HORAS_EXTRA = {
    5: ('hed', 25),      # extra diurna
    6: ('hen', 75),      # extra nocturna
    2: ('hrn', 35),      # hora nocturna
    9: ('hrn', 35),      # recargo nocturno
    7: ('heddf', 100),   # extra festiva diurna
    3: ('hrddf', 75),    # festiva diurna
    10: ('hrddf', 75),   # recargo festivo diurno
    8: ('hendf', 150),   # extra festiva nocturna
    4: ('hrndf', 110),   # festiva nocturna
    11: ('hrndf', 110),  # recargo festivo nocturno
}


class NominaElectronicaError(ValueError):
    """Un motivo para no generar o no emitir; va como `detail`, con `errores` por empleado."""

    def __init__(self, detail, errores=None):
        self.detail = detail
        self.errores = errores or []
        super().__init__(detail)


def _mes(anio, mes):
    try:
        desde = date(int(anio), int(mes), 1)
    except (TypeError, ValueError):
        raise NominaElectronicaError('El año y el mes deben ser una fecha válida.')
    return desde, date(desde.year, desde.month, calendar.monthrange(desde.year, desde.month)[1])


def _electronicas_del_mes(desde, hasta):
    return GenDocumento.objects.filter(
        documento_tipo_id=DOCUMENTO_TIPO_NOMINA_ELECTRONICA,
        fecha_desde=desde, fecha_hasta=hasta, estado_anulado=False,
    )


# --------------------------------------------------------------- generar ----

def generar(anio, mes):
    """
    Crea las nóminas electrónicas del mes, una por empleado. Todo o nada: si a
    un empleado le falta algo, no se crea ninguna y `errores` dice a quién.

    Un empleado que ya tiene electrónica en el mes y nóminas nuevas sin reportar
    es un error: hay que desgenerar (si no se envió) y volver a generar, porque
    la DIAN espera un solo documento por empleado y periodo.
    """
    desde, hasta = _mes(anio, mes)
    with transaction.atomic():
        nominas = list(
            GenDocumento.objects.select_for_update(of=('self',))
            .select_related('contacto', 'contrato', 'documento_tipo')
            .filter(
                documento_tipo__documento_clase_id=DOCUMENTO_CLASE_NOMINA,
                estado_aprobado=True, estado_anulado=False,
                fecha__range=(desde, hasta), documento_referencia__isnull=True,
            )
            .order_by('contacto_id', 'fecha', 'id')
        )
        if not nominas:
            raise NominaElectronicaError('No hay nóminas aprobadas sin reportar en el mes.')

        por_empleado = defaultdict(list)
        for nomina in nominas:
            por_empleado[nomina.contacto_id].append(nomina)

        con_electronica = set(
            _electronicas_del_mes(desde, hasta).values_list('contacto_id', flat=True)
        )
        errores = []
        for contacto_id, suyas in por_empleado.items():
            contacto = suyas[0].contacto
            nombre = contacto.nombre_corto if contacto else f'contacto {contacto_id}'
            if contacto is None:
                errores.append({'contacto_id': None, 'mensaje': f'Las nóminas {[n.numero for n in suyas]} no tienen empleado.'})
            elif contacto_id in con_electronica:
                errores.append({'contacto_id': contacto_id, 'mensaje': (
                    f'{nombre} ya tiene nómina electrónica en el mes y nóminas nuevas sin reportar: '
                    'desgenere y vuelva a generar.'
                )})
            elif not contacto.nombre1 or not contacto.apellido1:
                errores.append({'contacto_id': contacto_id, 'mensaje': f'{nombre} no tiene nombre1 o apellido1.'})
            elif suyas[-1].contrato is None:
                errores.append({'contacto_id': contacto_id, 'mensaje': f'La nómina {suyas[-1].numero} de {nombre} no tiene contrato.'})
        if errores:
            raise NominaElectronicaError(
                'Hay empleados a los que no se les puede generar la nómina electrónica.', errores,
            )

        tipo = GenDocumentoTipo.objects.get(pk=DOCUMENTO_TIPO_NOMINA_ELECTRONICA)
        generados = []
        for contacto_id, suyas in por_empleado.items():
            generados.append(_crear_electronica(tipo, desde, hasta, suyas))
        for documento in generados:
            # Asigna el consecutivo y corre las reglas de aprobación (nombre y
            # apellido separados, detalles).
            servicio_documento.aprobar(documento.id)
            documento.refresh_from_db()
    return generados


def _crear_electronica(tipo, desde, hasta, nominas):
    # El contrato de la última nómina del mes: si el empleado cambió de contrato,
    # el salario y las condiciones que se reportan son las vigentes al cierre.
    contrato = nominas[-1].contrato
    suma = lambda campo: sum((getattr(n, campo) for n in nominas), CERO)  # noqa: E731
    documento = GenDocumento.objects.create(
        documento_tipo=tipo,
        fecha=hasta, fecha_contable=hasta, fecha_desde=desde, fecha_hasta=hasta,
        contacto_id=nominas[0].contacto_id, contrato=contrato,
        salario=contrato.salario,
        base_cotizacion=suma('base_cotizacion'), base_prestacion=suma('base_prestacion'),
        devengado=suma('devengado'), deduccion=suma('deduccion'), total=suma('total'),
    )
    GenDocumentoDetalle.objects.bulk_create([
        GenDocumentoDetalle(
            documento=documento, tipo_registro='E', contrato_id=nomina.contrato_id,
            numero=nomina.numero, detalle=f'{nomina.documento_tipo.nombre} {nomina.numero}',
            base_cotizacion=nomina.base_cotizacion, base_prestacion=nomina.base_prestacion,
            devengado=nomina.devengado, deduccion=nomina.deduccion, total=nomina.total,
        )
        for nomina in nominas
    ])
    GenDocumento.objects.filter(pk__in=[n.pk for n in nominas]).update(documento_referencia=documento)
    return documento


# ------------------------------------------------------------ desgenerar ----

def desgenerar(anio, mes):
    """
    Borra las nóminas electrónicas del mes que no se han enviado y libera sus
    nóminas. Las enviadas se quedan: ya están en la DIAN, y lo que las corrige es
    una nota de ajuste. Devuelve cuántas borró y cuántas se quedaron.
    """
    desde, hasta = _mes(anio, mes)
    with transaction.atomic():
        electronicas = _electronicas_del_mes(desde, hasta).select_for_update()
        borrar = [d.pk for d in electronicas if not d.estado_electronico_enviado]
        enviadas = len(electronicas) - len(borrar)
        if not borrar:
            raise NominaElectronicaError(
                'No hay nóminas electrónicas sin enviar en el mes.' if enviadas
                else 'No hay nóminas electrónicas generadas en el mes.'
            )
        GenDocumento.objects.filter(documento_referencia_id__in=borrar).update(documento_referencia=None)
        GenDocumentoDetalle.objects.filter(documento_id__in=borrar).delete()
        GenDocumento.objects.filter(pk__in=borrar).delete()
    return {'eliminados': len(borrar), 'enviados': enviadas}


# ----------------------------------------------------------------- armar ----

def _decimal(valor):
    return str(Decimal(valor or 0).quantize(Decimal('0.01')))


def armar(documento, parametro):
    """
    El payload de `POST /api/nomina/nomina/` de rededoc. Levanta
    `NominaElectronicaError` con todo lo que falta, para corregirlo de una vez.
    """
    errores = []
    contacto = documento.contacto
    contrato = documento.contrato
    if documento.numero is None:
        errores.append(f'El documento {documento.id} no tiene número.')
    if contacto is None or contrato is None:
        raise NominaElectronicaError('No se puede emitir', [
            f'El documento {documento.id} no tiene empleado o contrato.'
        ])

    empleado = _empleado(contacto, contrato, errores)
    periodo = PERIODO_NOMINA.get(getattr(contrato.grupo, 'periodo_id', None))
    if periodo is None:
        errores.append(f'El grupo del contrato {contrato.id} no tiene un periodo de pago que reportar.')

    nominas = list(
        GenDocumento.objects.filter(documento_referencia=documento).order_by('fecha', 'id')
    )
    lineas = (
        GenDocumentoDetalle.objects
        .filter(documento__in=nominas, concepto__isnull=False)
        .select_related('concepto', 'novedad__novedad_tipo', 'documento')
        .order_by('documento__fecha', 'id')
    )
    conceptos = _conceptos(lineas, documento, errores)

    devengados = sum(
        (Decimal(c['valor']) + Decimal(c.get('valor_no_salarial') or 0)
         for c in conceptos if c['grupo'] == DEVENGADO), CERO,
    )
    deducciones = sum((Decimal(c['valor']) for c in conceptos if c['grupo'] == DEDUCCION), CERO)
    # Lo que se reporta tiene que ser lo que se pagó: si no cuadra, alguna línea
    # de las nóminas no se convirtió en concepto.
    if devengados != documento.devengado.quantize(Decimal('0.01')):
        errores.append(
            f'Los conceptos reportados suman {devengados} de devengado y las nóminas {documento.devengado}.'
        )
    if deducciones != documento.deduccion.quantize(Decimal('0.01')):
        errores.append(
            f'Los conceptos reportados suman {deducciones} de deducción y las nóminas {documento.deduccion}.'
        )
    if errores:
        raise NominaElectronicaError('No se puede emitir', errores)

    inicio = max(documento.fecha_desde, contrato.fecha_desde)
    retiro = (
        contrato.fecha_hasta
        if contrato.estado_terminado and documento.fecha_desde <= contrato.fecha_hasta <= documento.fecha_hasta
        else None
    )
    fin = retiro or documento.fecha_hasta
    ahora = timezone.localtime()
    payload = {
        'emisor': parametro.gen_rededoc_emisor,
        'ambiente': settings.REDEDOC_AMBIENTE,
        'empleado': empleado,
        'prefijo': PREFIJO,
        'consecutivo': documento.numero,
        'tipo_xml': TIPO_XML_NOMINA,
        'periodo_nomina': periodo,
        'fecha_liquidacion_inicio': inicio.isoformat(),
        'fecha_liquidacion_fin': fin.isoformat(),
        # Días desde el ingreso, en 30/360 como el resto de la nómina.
        'tiempo_laborado': dias_prestacionales(contrato.fecha_desde, fin),
        # Rededoc las reescribe al firmar; se mandan porque son obligatorias.
        'fecha_generacion': ahora.date().isoformat(),
        'hora_generacion': ahora.strftime('%H:%M:%S'),
        'fecha_pago': max(n.fecha for n in nominas).isoformat(),
        'moneda': MONEDA_COP,
        'total_devengados': _decimal(devengados),
        'total_deducciones': _decimal(deducciones),
        'redondeo': _decimal(CERO),
        'total_comprobante': _decimal(devengados - deducciones),
        'conceptos': conceptos,
    }
    if retiro:
        payload['fecha_retiro'] = retiro.isoformat()
    return payload


def _empleado(contacto, contrato, errores):
    tipo_cotizante = getattr(contrato.tipo_cotizante, 'codigo', None)
    tipo_trabajador = TIPO_TRABAJADOR.get(tipo_cotizante)
    if tipo_trabajador is None:
        errores.append(
            f'El tipo de cotizante {tipo_cotizante or "(vacío)"} del contrato {contrato.id} '
            'no se reporta en nómina electrónica.'
        )
    subtipo = getattr(contrato.subtipo_cotizante, 'codigo', None)
    tipo_contrato = TIPO_CONTRATO.get(contrato.contrato_tipo_id)
    if tipo_contrato is None:
        errores.append(f'El tipo de contrato del contrato {contrato.id} no tiene equivalente en la DIAN.')

    ciudad = contrato.ciudad_labora or contacto.ciudad
    if ciudad is None:
        errores.append(f'El contrato {contrato.id} no tiene ciudad donde labora.')
    configuracion = GenConfiguracion.objects.filter(pk=1).first()
    direccion = getattr(configuracion, 'gen_empresa_direccion', None)
    if not direccion:
        errores.append('La empresa no tiene dirección (lugar de trabajo del empleado).')

    con_cuenta = bool(contacto.numero_cuenta)
    datos = {
        'tipo_identificacion': int(contacto.identificacion.codigo),
        'numero_documento': contacto.numero_identificacion,
        'primer_apellido': contacto.apellido1 or '',
        'segundo_apellido': contacto.apellido2 or '',
        'primer_nombre': contacto.nombre1 or '',
        'otros_nombres': contacto.nombre2 or '',
        'codigo_trabajador': str(contacto.id),
        'tipo_trabajador': tipo_trabajador,
        'subtipo_trabajador': SUBTIPO_TRABAJADOR[SUBTIPO_PENSIONADO if subtipo == SUBTIPO_PENSIONADO else '00'],
        'tipo_contrato': tipo_contrato,
        'alto_riesgo_pension': False,
        'salario_integral': contrato.salario_integral,
        'sueldo': _decimal(contrato.salario),
        'fecha_ingreso': contrato.fecha_desde.isoformat(),
        'pais': ciudad.estado.pais_id if ciudad else None,
        'departamento': ciudad.estado_id if ciudad else None,
        'municipio': ciudad.id if ciudad else None,
        'direccion': direccion or '',
        'forma_pago': FORMA_PAGO_CONTADO,
        'medio_pago': MEDIO_PAGO_CONSIGNACION if con_cuenta else MEDIO_PAGO_EFECTIVO,
    }
    if con_cuenta:
        datos['banco'] = getattr(contacto.banco, 'nombre', '') or ''
        datos['tipo_cuenta'] = TIPO_CUENTA.get(contacto.cuenta_banco_clase_id, '')
        datos['numero_cuenta'] = contacto.numero_cuenta
    return datos


def _fechas_novedad(linea, documento):
    """
    Las fechas de la novedad, acotadas al periodo de su nómina. Una incapacidad
    sale en dos líneas —lo que paga la empresa y lo que paga la entidad, cada una
    con su concepto—, y cada una lleva las fechas de su tramo: con las de la
    novedad entera las dos se solaparían.
    """
    novedad = linea.novedad
    if novedad is None:
        return {}
    desde, hasta = novedad.fecha_desde, novedad.fecha_hasta
    tipo = novedad.novedad_tipo
    if tipo is not None and linea.concepto_id == tipo.concepto_id and novedad.fecha_desde_empresa:
        desde, hasta = novedad.fecha_desde_empresa, novedad.fecha_hasta_empresa
    elif tipo is not None and linea.concepto_id == tipo.concepto2_id and novedad.fecha_desde_entidad:
        desde, hasta = novedad.fecha_desde_entidad, novedad.fecha_hasta_entidad
    # Se acotan al periodo de la nómina que pagó la línea, que es lo que pagó.
    periodo_desde = linea.documento.fecha_desde or documento.fecha_desde
    periodo_hasta = linea.documento.fecha_hasta or documento.fecha_hasta
    inicio, fin = max(desde, periodo_desde), min(hasta, periodo_hasta)
    if inicio > fin:
        inicio, fin = periodo_desde, periodo_hasta
    return {'fecha_inicio': inicio.isoformat(), 'fecha_fin': fin.isoformat()}


def _conceptos(lineas, documento, errores):
    sumados = {}
    filas = []
    for linea in lineas:
        concepto = linea.concepto
        tipo = concepto.concepto_tipo_id
        # La licencia no remunerada no paga (operación 0) pero se reporta.
        if linea.operacion == 0 and tipo != 17:
            continue

        if tipo in SUMADOS:
            grupo, codigo = SUMADOS[tipo]
            fila = sumados.setdefault(codigo, {'grupo': grupo, 'concepto': codigo, 'valor': CERO})
            fila['valor'] += linea.pago
            # Básico y prima reportan días; los demás solo el valor.
            if codigo in ('basico', 'prima'):
                fila['cantidad'] = fila.get('cantidad', CERO) + linea.dias
            if codigo in ('salud', 'fondo_pension', 'fondo_sp'):
                fila['porcentaje'] = linea.porcentaje
            if codigo == 'intereses_cesantias':
                fila['porcentaje'] = PORCENTAJE_INTERESES
        elif tipo in CON_FECHAS:
            fila = {
                'grupo': DEVENGADO, 'concepto': CON_FECHAS[tipo],
                'cantidad': _decimal(linea.dias),
                'valor': _decimal(linea.pago if tipo != 17 else CERO),
                **_fechas_novedad(linea, documento),
            }
            if tipo in TIPO_INCAPACIDAD:
                fila['tipo_incapacidad'] = TIPO_INCAPACIDAD[tipo]
            filas.append(fila)
        elif tipo == CONCEPTO_TIPO_VACACIONES_DINERO:
            filas.append({'grupo': DEVENGADO, 'concepto': 'vacaciones_compensadas',
                          'cantidad': _decimal(linea.dias), 'valor': _decimal(linea.pago)})
        elif tipo == CONCEPTO_TIPO_EXTRAS and concepto.id in HORAS_EXTRA:
            codigo, recargo = HORAS_EXTRA[concepto.id]
            filas.append({'grupo': DEVENGADO, 'concepto': codigo, 'cantidad': _decimal(linea.cantidad),
                          'porcentaje': _decimal(recargo), 'valor': _decimal(linea.pago)})
        elif concepto.id == CONCEPTO_COMISION:
            filas.append({'grupo': DEVENGADO, 'concepto': 'comision', 'valor': _decimal(linea.pago)})
        elif tipo == CONCEPTO_TIPO_SALARIAL:
            filas.append({'grupo': DEVENGADO, 'concepto': 'otro_concepto', 'descripcion': concepto.nombre,
                          'valor': _decimal(linea.pago)})
        elif tipo == CONCEPTO_TIPO_NO_SALARIAL:
            filas.append({'grupo': DEVENGADO, 'concepto': 'otro_concepto', 'descripcion': concepto.nombre,
                          'valor': _decimal(CERO), 'valor_no_salarial': _decimal(linea.pago)})
        elif tipo == CONCEPTO_TIPO_DESCUENTO:
            filas.append({'grupo': DEDUCCION, 'concepto': 'otra_deduccion', 'valor': _decimal(linea.pago)})
        else:
            errores.append(
                f'El concepto {concepto.nombre} de la nómina {linea.documento.numero} no tiene '
                'equivalente en la nómina electrónica.'
            )

    for fila in sumados.values():
        for campo in ('valor', 'cantidad', 'porcentaje'):
            if campo in fila:
                fila[campo] = _decimal(fila[campo])
    return list(sumados.values()) + filas
