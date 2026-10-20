"""
Liquidación de una novedad (incapacidad, licencia o vacaciones): calcula lo que
la nómina paga por ella y lo guarda en la propia novedad. Portado de
`liquidar_novedad` de itrio.

La nómina (`nomina._novedades`) no recalcula nada: lee de aquí los días, las
fechas y el valor hora de cada tramo (`*_empresa`, `*_entidad`) y, en vacaciones,
el valor día de disfrute y de dinero. Una novedad sin liquidar paga cero.

- Incapacidad general (1): la empresa paga los 2 primeros días y la entidad el
  resto; en una prórroga la empresa solo completa lo que falte de esos 2 días.
- Incapacidad laboral (2): todo la entidad.
- Licencia maternidad o paternidad (3): todo la entidad.
- Licencia de luto y remunerada (4, 5): todo la empresa, sin porcentaje.
- Licencia no remunerada (6): no paga.
- Vacaciones (7): un día de salario por día disfrutado y por día en dinero; lo de
  dinero se reparte entre los días disfrutados, que es como la nómina lo paga.

Incapacidades y licencia de maternidad pagan sobre la base de cotización: el
salario, el mínimo en aprendiz del SENA y práctica estudiantil, o `base_cotizacion_propuesto` si
viene; las demás, sobre el salario. Las incapacidades no pagan un día por debajo
del día mínimo.
"""
from datetime import timedelta
from decimal import Decimal

from general.models import GenConfiguracion
from humano.servicios.nomina import (
    NOVEDAD_TIPO_LICENCIA_MATERNIDAD,
    NOVEDAD_TIPO_VACACION,
    NOVEDAD_TIPOS_INCAPACIDAD,
    NOVEDAD_TIPOS_LICENCIA_EMPRESA,
    redondear,
)

NOVEDAD_TIPO_INCAPACIDAD_GENERAL = 1
# Aprendiz del SENA y práctica estudiantil: su base es el salario mínimo.
CONTRATO_TIPOS_BASE_MINIMO = (4, 5)
# Días de una incapacidad general que paga la empresa.
DIAS_EMPRESA_INCAPACIDAD = 2

_SEIS = Decimal('0.000001')
_CERO = Decimal('0')

# Lo que calcula `liquidar`; todo lo demás de la novedad es dato del usuario.
CAMPOS_CALCULADOS = (
    'dias', 'dias_acumulados', 'prorroga', 'base_cotizacion',
    'dias_empresa', 'hora_empresa', 'pago_empresa', 'fecha_desde_empresa', 'fecha_hasta_empresa',
    'dias_entidad', 'hora_entidad', 'pago_entidad', 'fecha_desde_entidad', 'fecha_hasta_entidad',
    'pago_dia_disfrute', 'pago_disfrute', 'pago_dia_dinero', 'pago_dinero', 'total',
)


class NovedadError(ValueError):
    """Un motivo por el que la novedad no se puede liquidar; va como `detail`."""

    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


def _seis(valor):
    return Decimal(valor).quantize(_SEIS)


def _base_cotizacion(novedad, configuracion):
    if novedad.base_cotizacion_propuesto > 0:
        return novedad.base_cotizacion_propuesto
    if novedad.contrato.contrato_tipo_id in CONTRATO_TIPOS_BASE_MINIMO:
        return configuracion.hum_salario_minimo
    return novedad.contrato.salario


def _dias_incapacidad(novedad, dias):
    """(días empresa, días entidad) de una incapacidad, con la prórroga en cuenta."""
    if novedad.novedad_tipo_id != NOVEDAD_TIPO_INCAPACIDAD_GENERAL:
        return 0, dias
    if not novedad.prorroga:
        empresa = min(dias, DIAS_EMPRESA_INCAPACIDAD)
        return empresa, dias - empresa
    # La empresa ya pagó en la incapacidad anterior lo que lleva acumulado.
    pendiente_empresa = max(DIAS_EMPRESA_INCAPACIDAD - novedad.novedad_referencia.dias_acumulados, 0)
    empresa = min(dias, pendiente_empresa)
    return empresa, dias - empresa


def _dia_incapacidad(valor_dia, concepto, dia_minimo):
    dia = valor_dia * (concepto.porcentaje if concepto else _CERO) / 100
    return max(dia, dia_minimo)


def cargar_configuracion():
    """La configuración de nómina que necesita el cálculo, o `NovedadError` si falta."""
    configuracion = GenConfiguracion.objects.filter(pk=1).first()
    if configuracion is None:
        raise NovedadError('Falta la configuración general de la empresa.')
    if not configuracion.hum_factor or not configuracion.hum_salario_minimo:
        raise NovedadError('Falta el factor de horas o el salario mínimo en la configuración.')
    return configuracion


def liquidar(novedad):
    """Calcula y guarda los valores de la novedad. Devuelve la novedad."""
    calcular(novedad, cargar_configuracion())
    novedad.save(update_fields=list(CAMPOS_CALCULADOS))
    return novedad


def calcular(novedad, configuracion):
    """
    Llena los `CAMPOS_CALCULADOS` de la novedad sin guardarla: así el importar
    calcula cada fila y las crea todas en un `bulk_create`.
    """
    factor = configuracion.hum_factor
    dia_minimo = configuracion.hum_salario_minimo / 30
    hora_minimo = dia_minimo / factor
    tipo = novedad.novedad_tipo_id
    dias = (novedad.fecha_hasta - novedad.fecha_desde).days + 1

    valores = {campo: _CERO for campo in CAMPOS_CALCULADOS}
    valores.update({
        'fecha_desde_empresa': None, 'fecha_hasta_empresa': None,
        'fecha_desde_entidad': None, 'fecha_hasta_entidad': None,
    })
    novedad.prorroga = novedad.novedad_referencia_id is not None
    if tipo in NOVEDAD_TIPOS_INCAPACIDAD or tipo == NOVEDAD_TIPO_LICENCIA_MATERNIDAD:
        base = _base_cotizacion(novedad, configuracion)
    else:
        base = novedad.contrato.salario
    valor_dia = base / 30

    if tipo in NOVEDAD_TIPOS_INCAPACIDAD:
        dias_empresa, dias_entidad = _dias_incapacidad(novedad, dias)
        tramos = (
            ('empresa', dias_empresa, novedad.novedad_tipo.concepto, novedad.fecha_desde),
            ('entidad', dias_entidad, novedad.novedad_tipo.concepto2,
             novedad.fecha_desde + timedelta(days=dias_empresa)),
        )
        for lado, dias_tramo, concepto, desde in tramos:
            if dias_tramo <= 0:
                continue
            dia = _dia_incapacidad(valor_dia, concepto, dia_minimo)
            valores[f'dias_{lado}'] = dias_tramo
            valores[f'hora_{lado}'] = _seis(max(dia / factor, hora_minimo))
            valores[f'pago_{lado}'] = _seis(dias_tramo * dia)
            valores[f'fecha_desde_{lado}'] = desde
            valores[f'fecha_hasta_{lado}'] = desde + timedelta(days=dias_tramo - 1)

    elif tipo == NOVEDAD_TIPO_LICENCIA_MATERNIDAD:
        concepto = novedad.novedad_tipo.concepto
        dia = valor_dia * (concepto.porcentaje if concepto else _CERO) / 100
        valores.update({
            'dias_entidad': dias,
            'hora_entidad': _seis(dia / factor),
            'pago_entidad': _seis(dias * dia),
            'fecha_desde_entidad': novedad.fecha_desde,
            'fecha_hasta_entidad': novedad.fecha_hasta,
        })

    elif tipo in NOVEDAD_TIPOS_LICENCIA_EMPRESA:
        valores.update({
            'dias_empresa': dias,
            'hora_empresa': _seis(valor_dia / factor),
            'pago_empresa': _seis(dias * valor_dia),
            'fecha_desde_empresa': novedad.fecha_desde,
            'fecha_hasta_empresa': novedad.fecha_hasta,
        })

    elif tipo == NOVEDAD_TIPO_VACACION:
        if novedad.dias_disfrutados_reales <= 0:
            raise NovedadError('Las vacaciones necesitan días disfrutados reales mayores que cero.')
        pago_disfrute = redondear(valor_dia * novedad.dias_disfrutados_reales)
        pago_dinero = redondear(valor_dia * novedad.dias_dinero)
        valores.update({
            'pago_dia_disfrute': _seis(valor_dia),
            'pago_disfrute': pago_disfrute,
            'pago_dinero': pago_dinero,
            # La nómina paga el dinero por día disfrutado, junto con el disfrute.
            'pago_dia_dinero': _seis(pago_dinero / novedad.dias_disfrutados_reales),
        })

    valores['total'] = (
        valores['pago_empresa'] + valores['pago_entidad']
        + valores['pago_disfrute'] + valores['pago_dinero']
    )
    valores['dias'] = dias
    valores['base_cotizacion'] = base
    valores['prorroga'] = novedad.prorroga
    valores['dias_acumulados'] = (
        novedad.novedad_referencia.dias_acumulados + dias if novedad.prorroga else dias
    )

    for campo, valor in valores.items():
        setattr(novedad, campo, valor)
    return novedad
