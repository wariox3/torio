"""
El archivo plano de la PILA (Planilla Integrada de Liquidación de Aportes) de un
aporte, para subirlo al operador de información.

Formato de la Resolución 2388 de 2016: un registro tipo 01 con el aportante y
uno tipo 02 por cada línea del aporte. Cada campo tiene ancho fijo; los
comentarios `#n` son el número de campo de la resolución. El archivo va en
Windows-1252, que es lo que leen los operadores.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from general.models import GenConfiguracion
from humano.models import HumAporteDetalle

# Valores fijos de la planilla. Hoy son iguales para todos los aportantes; si
# alguno cambia por empresa, pasan a `GenConfiguracion`.
TIPO_PLANILLA = 'E'          # Empleados
TIPO_APORTANTE = '01'        # Empleador
CODIGO_OPERADOR = '88'
EXONERADO_LEY_1607 = 'S'     # Exonerado de salud, SENA e ICBF
ACTIVIDAD_ECONOMICA = '1620101'


class PilaError(ValueError):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


def _texto(valor, largo, relleno=' ', izquierda=False):
    """El valor a ancho fijo: se corta si sobra y se rellena si falta."""
    texto = '' if valor is None else str(valor)
    texto = texto[:largo]
    return texto.rjust(largo, relleno) if izquierda else texto.ljust(largo, relleno)


def _numero(valor, largo):
    """Pesos enteros, con ceros a la izquierda."""
    entero = int(Decimal(valor or 0).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return _texto(entero, largo, '0', izquierda=True)


def _tarifa(porcentaje, largo):
    """La tarifa como fracción («16» → «0.16000»), con tantos decimales como quepan."""
    fraccion = Decimal(porcentaje or 0) / 100
    return f'{fraccion:.{largo - 2}f}'[:largo]


def _marca(valor, si='X'):
    return si if valor else ' '


def generar_plano(aporte):
    """Devuelve `(contenido, nombre)` del archivo plano del aporte."""
    if not aporte.estado_generado:
        raise PilaError('El aporte no está generado.')
    configuracion = GenConfiguracion.objects.filter(pk=1).first()
    if configuracion is None:
        raise PilaError('Falta la configuración general de la empresa.')
    if aporte.entidad_riesgo is None:
        raise PilaError('El aporte no tiene administradora de riesgos laborales.')

    por_sucursal = aporte.presentacion == 'S' and aporte.sucursal is not None
    lineas = [''.join([
        '01',                                                    # 1 Tipo de registro
        '1',                                                     # 2 Modalidad de la planilla
        '0001',                                                  # 3 Secuencia
        _texto(configuracion.gen_empresa_nombre_corto, 200),     # 4 Razón social del aportante
        'NI',                                                    # 5 Tipo de documento del aportante
        _texto(configuracion.gen_empresa_numero_identificacion, 16),  # 6 Número de identificación
        _texto(configuracion.gen_empresa_digito_verificacion, 1),     # 7 Dígito de verificación
        TIPO_PLANILLA,                                           # 8 Tipo de planilla
        _texto('', 10),                                          # 9 Planilla asociada
        _texto('', 10),                                          # 10 Fecha de pago planilla asociada
        _texto(aporte.presentacion, 1),                          # 11 Forma de presentación
        _texto(aporte.sucursal.codigo if por_sucursal else '', 10, izquierda=True),  # 12 Código sucursal
        _texto(aporte.sucursal.nombre if por_sucursal else '', 40),                  # 13 Nombre sucursal
        _texto(aporte.entidad_riesgo.codigo, 6),                 # 14 Código de la ARL
        f'{aporte.anio}-{aporte.mes:02d}',                       # 15 Periodo de pago (no salud)
        f'{aporte.anio_salud}-{aporte.mes_salud:02d}',           # 16 Periodo de pago salud
        _texto('', 10),                                          # 17 Número de radicación
        _texto('', 10),                                          # 18 Fecha de pago
        _numero(aporte.empleados, 5),                            # 19 Número total de empleados
        _numero(aporte.base_cotizacion, 12),                     # 20 Valor total de la nómina
        TIPO_APORTANTE,                                          # 21 Tipo de aportante
        CODIGO_OPERADOR,                                         # 22 Código del operador
    ])]

    detalles = (
        HumAporteDetalle.objects.filter(aporte_contrato__aporte=aporte)
        .select_related(
            'aporte_contrato__contrato__contacto__identificacion',
            'aporte_contrato__contrato__tipo_cotizante',
            'aporte_contrato__contrato__subtipo_cotizante',
            'aporte_contrato__ciudad_labora__estado',
            'aporte_contrato__entidad_pension',
            'aporte_contrato__entidad_salud',
            'aporte_contrato__entidad_caja',
            'aporte_contrato__riesgo',
        )
        .order_by('aporte_contrato_id', 'id')
    )
    for secuencia, detalle in enumerate(detalles, start=1):
        lineas.append(_registro_cotizante(secuencia, detalle, aporte))

    contenido = '\n'.join(lineas) + '\n'
    nombre = f"pila{timezone.localtime().strftime('%Y%m%d%H%M%S')}.txt"
    return contenido.encode('cp1252', errors='replace'), nombre


def _registro_cotizante(secuencia, detalle, aporte):
    """El registro tipo 02 de una línea del aporte."""
    aporte_contrato = detalle.aporte_contrato
    contrato = aporte_contrato.contrato
    contacto = contrato.contacto
    ciudad = aporte_contrato.ciudad_labora
    codigo = (lambda objeto: objeto.codigo if objeto is not None else '')
    vacaciones = 'L' if detalle.licencia_remunerada else _marca(detalle.vacaciones)

    return ''.join([
        '02',                                                         # 1 Tipo de registro
        _numero(secuencia, 5),                                        # 2 Secuencia
        _texto(contacto.identificacion.aporte if contacto.identificacion else '', 2),  # 3 Tipo de documento
        _texto(contacto.numero_identificacion, 16),                   # 4 Número de identificación
        _texto(codigo(contrato.tipo_cotizante), 2, '0', izquierda=True),     # 5 Tipo de cotizante
        _texto(codigo(contrato.subtipo_cotizante), 2, '0', izquierda=True),  # 6 Subtipo de cotizante
        ' ',                                                          # 7 Extranjero no obligado a pensión
        ' ',                                                          # 8 Colombiano en el exterior
        _texto(codigo(ciudad.estado) if ciudad else '', 2, '0', izquierda=True),  # 9 Departamento
        _texto((ciudad.codigo or '')[-3:] if ciudad else '', 3, '0', izquierda=True),  # 10 Municipio
        _texto(contacto.apellido1, 20),                               # 11 Primer apellido
        _texto(contacto.apellido2, 30),                               # 12 Segundo apellido
        _texto(contacto.nombre1, 20),                                 # 13 Primer nombre
        _texto(contacto.nombre2, 30),                                 # 14 Segundo nombre
        _marca(aporte_contrato.ingreso),                              # 15 ING
        _marca(aporte_contrato.retiro),                               # 16 RET
        ' ', ' ', ' ', ' ',                                           # 17-20 Traslados (TDE, TAE, TDP, TAP)
        _marca(detalle.variacion_permanente_salario),                 # 21 VSP
        ' ',                                                          # 22 Correcciones
        _marca(detalle.variacion_transitoria_salario),                # 23 VST
        _marca(detalle.suspension_temporal_contrato),                 # 24 SLN
        _marca(detalle.incapacidad_general),                          # 25 IGE
        _marca(detalle.licencia_maternidad),                          # 26 LMA
        vacaciones,                                                   # 27 VAC-LR
        _marca(detalle.aporte_voluntario_pension),                    # 28 AVP
        _marca(detalle.variacion_centro_trabajo),                     # 29 VCT
        _numero(detalle.dias_incapacidad_laboral, 2),                 # 30 IRL
        _texto(codigo(aporte_contrato.entidad_pension), 6),           # 31 Administradora de pensiones
        _texto('', 6),                                                # 32 AFP a la que se traslada
        _texto(codigo(aporte_contrato.entidad_salud), 6),             # 33 EPS
        _texto('', 6),                                                # 34 EPS a la que se traslada
        _texto(codigo(aporte_contrato.entidad_caja), 6),              # 35 Caja de compensación
        _numero(detalle.dias_pension, 2),                             # 36 Días cotizados a pensión
        _numero(detalle.dias_salud, 2),                               # 37 Días cotizados a salud
        _numero(detalle.dias_riesgos, 2),                             # 38 Días cotizados a riesgos
        _numero(detalle.dias_caja, 2),                                # 39 Días cotizados a caja
        _numero(aporte_contrato.salario, 9),                          # 40 Salario básico
        'X' if detalle.salario_integral else 'F',                     # 41 Salario integral
        _numero(detalle.base_cotizacion_pension, 9),                  # 42 IBC pensión
        _numero(detalle.base_cotizacion_salud, 9),                    # 43 IBC salud
        _numero(detalle.base_cotizacion_riesgos, 9),                  # 44 IBC riesgos
        _numero(detalle.base_cotizacion_caja, 9),                     # 45 IBC caja
        _tarifa(detalle.tarifa_pension, 7),                           # 46 Tarifa pensiones
        _numero(detalle.cotizacion_pension, 9),                       # 47 Cotización pensiones
        _numero(detalle.cotizacion_voluntario_pension_afiliado, 9),   # 48 Voluntario afiliado
        _numero(detalle.cotizacion_voluntario_pension_aportante, 9),  # 49 Voluntario aportante
        _numero(                                                      # 50 Total pensiones (47 + 48 + 49)
            detalle.cotizacion_pension + detalle.cotizacion_voluntario_pension_afiliado
            + detalle.cotizacion_voluntario_pension_aportante, 9,
        ),
        _numero(detalle.cotizacion_solidaridad_solidaridad, 9),       # 51 Fondo de solidaridad
        _numero(detalle.cotizacion_solidaridad_subsistencia, 9),      # 52 Fondo de subsistencia
        _numero(0, 9),                                                # 53 Valor no retenido por voluntarios
        _tarifa(detalle.tarifa_salud, 7),                             # 54 Tarifa salud
        _numero(detalle.cotizacion_salud, 9),                         # 55 Cotización salud
        _numero(detalle.upc_adicional, 9),                            # 56 UPC adicional
        _texto('', 15),                                               # 57 Autorización incapacidad
        _numero(0, 9),                                                # 58 Valor incapacidad
        _texto('', 15),                                               # 59 Autorización licencia maternidad
        _numero(0, 9),                                                # 60 Valor licencia maternidad
        _tarifa(detalle.tarifa_riesgos, 9),                           # 61 Tarifa riesgos
        _numero(0, 9),                                                # 62 Centro de trabajo
        _numero(detalle.cotizacion_riesgos, 9),                       # 63 Cotización riesgos
        _tarifa(detalle.tarifa_caja, 7),                              # 64 Tarifa caja
        _numero(detalle.cotizacion_caja, 9),                          # 65 Valor caja
        _tarifa(detalle.tarifa_sena, 7),                              # 66 Tarifa SENA
        _numero(detalle.cotizacion_sena, 9),                          # 67 Valor SENA
        _tarifa(detalle.tarifa_icbf, 7),                              # 68 Tarifa ICBF
        _numero(detalle.cotizacion_icbf, 9),                          # 69 Valor ICBF
        _tarifa(0, 7),                                                # 70 Tarifa ESAP
        _numero(0, 9),                                                # 71 Valor ESAP
        _tarifa(0, 7),                                                # 72 Tarifa MEN
        _numero(0, 9),                                                # 73 Valor MEN
        _texto('', 2),                                                # 74 Documento cotizante principal
        _texto('', 16),                                               # 75 Identificación cotizante principal
        EXONERADO_LEY_1607,                                           # 76 Exonerado Ley 1607
        _texto(aporte.entidad_riesgo.codigo, 6),                      # 77 ARL del afiliado
        _texto(aporte_contrato.riesgo_id or '', 1),                   # 78 Clase de riesgo
        ' ',                                                          # 79 Tarifa especial pensiones
        _texto(detalle.fecha_ingreso, 10),                            # 80 Fecha de ingreso
        _texto(detalle.fecha_retiro, 10),                             # 81 Fecha de retiro
        _texto(detalle.fecha_inicio_variacion_permanente_salario, 10),  # 82 Inicio VSP
        _texto(detalle.fecha_inicio_suspension_temporal_contrato, 10),  # 83 Inicio SLN
        _texto(detalle.fecha_fin_suspension_temporal_contrato, 10),     # 84 Fin SLN
        _texto(detalle.fecha_inicio_incapacidad_general, 10),           # 85 Inicio IGE
        _texto(detalle.fecha_fin_incapacidad_general, 10),              # 86 Fin IGE
        _texto(detalle.fecha_inicio_licencia_maternidad, 10),           # 87 Inicio LMA
        _texto(detalle.fecha_fin_licencia_maternidad, 10),              # 88 Fin LMA
        _texto(detalle.fecha_inicio_vacaciones, 10),                    # 89 Inicio VAC-LR
        _texto(detalle.fecha_fin_vacaciones, 10),                       # 90 Fin VAC-LR
        _texto('', 10),                                               # 91 Inicio VCT
        _texto('', 10),                                               # 92 Fin VCT
        _texto(detalle.fecha_inicio_incapacidad_laboral, 10),           # 93 Inicio IRL
        _texto(detalle.fecha_fin_incapacidad_laboral, 10),              # 94 Fin IRL
        _numero(detalle.base_cotizacion_otros_parafiscales, 9),       # 95 IBC otros parafiscales
        _numero(detalle.horas, 3),                                    # 96 Horas laboradas
        _texto('', 10),                                               # 97 Fecha radicación en el exterior
        ACTIVIDAD_ECONOMICA,                                          # 98 Actividad económica riesgos
    ])
