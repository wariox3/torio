"""
Estado de situación financiera formal: el que se presenta, con activo, pasivo y
patrimonio en secciones, sus subtotales y un corte anterior para comparar.

Convive con el informe `base` (`balance.estado_situacion_financiera`), que es una
fila por cuenta que movió en un rango, tal como sale de itrio.

Es un **corte**, no un rango: el saldo de cada cuenta es todo lo que acumuló
hasta `fecha_corte`, desde el primer movimiento —saldos iniciales y asientos de
cierre incluidos—. A diferencia del estado de resultados, acá el cierre sí entra:
es lo que traslada la utilidad del año al patrimonio.

La clasificación sigue la NIC 1 aproximada por el grupo del PUC (2 dígitos):

    activo corriente      11–14      activo no corriente   el resto de la clase 1
    pasivo corriente      21–26      pasivo no corriente   el resto de la clase 2
    patrimonio            clase 3

Un grupo que no esté en la lista de corrientes cae en no corriente, así que
ninguna cuenta de balance se queda por fuera. Es una aproximación: una
obligación financiera (21) a largo plazo sale como corriente.

**Resultado del ejercicio.** Mientras no se haga el cierre, la utilidad vive en
las clases 4 a 7, y sin ella el estado no cuadra. Se presenta como una línea del
patrimonio: el saldo acumulado de las clases 4 a 7 al corte más el del grupo 36
(resultados del ejercicio), que es donde el cierre la deja. Así la línea dice lo
mismo antes y después del cierre, y el activo iguala al pasivo más el
patrimonio en cualquier caso. Las cuentas de orden (8 y 9) no entran.

Cada sección se presenta en positivo en su naturaleza (el activo débito −
crédito, el pasivo y el patrimonio crédito − débito). Una cuenta correctora,
como la depreciación acumulada, sale negativa dentro del activo.

Igual que en el estado de resultados, cuando a la cuenta auxiliar le faltan los
FK de clase, grupo o cuenta se sacan del prefijo del código.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from contabilidad.models import ConCuentaCuenta, ConCuentaGrupo, ConMovimiento
from contabilidad.servicios.tablero import anio_anterior

_CERO = Decimal('0')
_CERO_SQL = Value(_CERO, output_field=DecimalField(max_digits=20, decimal_places=6))

CLASE_ACTIVO = 1
CLASE_PASIVO = 2
CLASE_PATRIMONIO = 3
CLASES_RESULTADO = (4, 5, 6, 7)
GRUPO_RESULTADO_EJERCICIO = 36
GRUPOS_ACTIVO_CORRIENTE = (11, 12, 13, 14)
GRUPOS_PASIVO_CORRIENTE = (21, 22, 23, 24, 25, 26)

# Nivel de detalle de las líneas.
CUENTA = 'cuenta'
GRUPO = 'grupo'
NIVELES = (CUENTA, GRUPO)

# Contra qué corte se compara.
CIERRE_ANTERIOR = 'cierre_anterior'
ANIO_ANTERIOR = 'anio_anterior'
NINGUNO = 'ninguno'
COMPARACIONES = (CIERRE_ANTERIOR, ANIO_ANTERIOR, NINGUNO)

# Tipos de fila, de arriba abajo.
SECCION = 'SECCION'              # ACTIVO, PASIVO, PATRIMONIO: título sin importes
SUBSECCION = 'SUBSECCION'        # corriente / no corriente: título sin importes
LINEA = 'LINEA'                  # una cuenta (4 dígitos) o un grupo (2)
RESULTADO = 'RESULTADO'          # el resultado del ejercicio, dentro del patrimonio
SUBTOTAL = 'SUBTOTAL'            # total corriente / no corriente
TOTAL = 'TOTAL'                  # total activo / pasivo / patrimonio
TOTAL_FINAL = 'TOTAL_FINAL'      # total pasivo y patrimonio

_DEBITO = 'D'
_CREDITO = 'C'

# (clave, título de la sección, naturaleza, subsecciones). Una subsección sin
# título no pinta encabezado ni subtotal: el patrimonio no se parte.
ESTRUCTURA = (
    ('activo', 'Activo', _DEBITO, (
        ('activo_corriente', 'Activo corriente'),
        ('activo_no_corriente', 'Activo no corriente'),
    )),
    ('pasivo', 'Pasivo', _CREDITO, (
        ('pasivo_corriente', 'Pasivo corriente'),
        ('pasivo_no_corriente', 'Pasivo no corriente'),
    )),
    ('patrimonio', 'Patrimonio', _CREDITO, (
        ('patrimonio', None),
    )),
)

NOMBRE_RESULTADO = 'Resultado del ejercicio'


def fecha_comparativo(fecha_corte, comparar):
    """El corte contra el que se compara, o `None` sin comparativo."""
    if comparar == CIERRE_ANTERIOR:
        return date(fecha_corte.year - 1, 12, 31)
    if comparar == ANIO_ANTERIOR:
        return anio_anterior(fecha_corte)
    return None


def agrupar(fecha_corte):
    """
    Débitos y créditos acumulados al corte por cuenta auxiliar, clases 1 a 7.

    Es el queryset sobre el que se aplican los filtros dinámicos, antes de que
    se agrupe. Sin piso de fecha y con los asientos de cierre: es un saldo.
    """
    return (
        ConMovimiento.objects
        .filter(fecha__lte=fecha_corte)
        .filter(
            Q(cuenta__cuenta_clase_id__in=(1, 2, 3, *CLASES_RESULTADO))
            | Q(cuenta__cuenta_clase__isnull=True, cuenta__codigo__regex=r'^[1-7]')
        )
        .values(
            'cuenta__codigo', 'cuenta__cuenta_clase_id',
            'cuenta__cuenta_grupo_id', 'cuenta__cuenta_cuenta_id',
        )
        .annotate(
            total_debito=Coalesce(Sum('debito'), _CERO_SQL),
            total_credito=Coalesce(Sum('credito'), _CERO_SQL),
        )
        .order_by('cuenta__codigo')
    )


def estado(actual, anterior=None, nivel=CUENTA):
    """
    `(filas, totales)` del estado.

    `actual` y `anterior` son el resultado (ya filtrado) de `agrupar` en cada
    corte; sin `anterior` las columnas de comparación salen nulas. Cada fila trae
    `tipo`, `codigo`, `nombre`, `actual`, `anterior`, `variacion` y `porcentaje`
    (fracción: 0.25 es 25 %); los títulos no traen importes.

    `totales` resume los dos cortes para el encabezado: los totales de cada
    sección y subsección, si cuadra y las razones financieras.
    """
    hay_anterior = anterior is not None
    saldos = {
        'actual': _clasificar(actual, nivel),
        'anterior': _clasificar(anterior, nivel) if hay_anterior else _vacio(),
    }
    nombres = _nombres(saldos, nivel)

    filas = []
    totales = {'actual': {}, 'anterior': {}}
    for clave_seccion, titulo, _, subsecciones in ESTRUCTURA:
        filas.append(_titulo(SECCION, titulo))
        for clave_sub, titulo_sub in subsecciones:
            if titulo_sub:
                filas.append(_titulo(SUBSECCION, titulo_sub))
            lineas = {
                periodo: saldos[periodo]['lineas'].get(clave_sub, {})
                for periodo in ('actual', 'anterior')
            }
            for codigo in sorted(set(lineas['actual']) | set(lineas['anterior'])):
                valor_actual = lineas['actual'].get(codigo, _CERO)
                valor_anterior = lineas['anterior'].get(codigo, _CERO)
                if valor_actual == 0 and valor_anterior == 0:
                    continue
                filas.append(_fila(
                    LINEA, codigo, nombres.get(codigo) or _nombre_por_defecto(codigo, nivel),
                    valor_actual, valor_anterior if hay_anterior else None,
                ))
            if clave_seccion == 'patrimonio':
                resultado = {p: saldos[p]['resultado'] for p in ('actual', 'anterior')}
                if resultado['actual'] or resultado['anterior']:
                    filas.append(_fila(
                        RESULTADO, '', NOMBRE_RESULTADO,
                        resultado['actual'], resultado['anterior'] if hay_anterior else None,
                    ))
            for periodo in ('actual', 'anterior'):
                subtotal = sum(lineas[periodo].values(), _CERO)
                if clave_seccion == 'patrimonio':
                    subtotal += saldos[periodo]['resultado']
                totales[periodo][clave_sub] = subtotal
            if titulo_sub:
                filas.append(_fila(
                    SUBTOTAL, '', f'Total {titulo_sub[0].lower()}{titulo_sub[1:]}',
                    totales['actual'][clave_sub],
                    totales['anterior'][clave_sub] if hay_anterior else None,
                ))
        for periodo in ('actual', 'anterior'):
            totales[periodo][clave_seccion] = sum(
                (totales[periodo][clave_sub] for clave_sub, _ in subsecciones), _CERO,
            )
        filas.append(_fila(
            TOTAL, '', f'Total {titulo.lower()}',
            totales['actual'][clave_seccion],
            totales['anterior'][clave_seccion] if hay_anterior else None,
        ))

    for periodo in ('actual', 'anterior'):
        totales[periodo]['pasivo_patrimonio'] = (
            totales[periodo]['pasivo'] + totales[periodo]['patrimonio']
        )
    filas.append(_fila(
        TOTAL_FINAL, '', 'Total pasivo y patrimonio',
        totales['actual']['pasivo_patrimonio'],
        totales['anterior']['pasivo_patrimonio'] if hay_anterior else None,
    ))
    return filas, {
        'actual': _resumen(totales['actual']),
        'anterior': _resumen(totales['anterior']) if hay_anterior else None,
    }


def _vacio():
    return {'lineas': {}, 'resultado': _CERO}


def _clasificar(agrupado, nivel):
    """
    `{'lineas': {subsección: {código: saldo}}, 'resultado': saldo}`.

    El código es el de la cuenta (4 dígitos) o el del grupo (2), según `nivel`.
    El saldo ya viene en la naturaleza de su sección.
    """
    lineas = defaultdict(lambda: defaultdict(lambda: _CERO))
    resultado = _CERO
    for fila in agrupado:
        codigo = fila['cuenta__codigo'] or ''
        clase = fila['cuenta__cuenta_clase_id'] or _prefijo(codigo, 1)
        grupo = fila['cuenta__cuenta_grupo_id'] or _prefijo(codigo, 2)
        cuenta = fila['cuenta__cuenta_cuenta_id'] or _prefijo(codigo, 4)
        credito_neto = fila['total_credito'] - fila['total_debito']

        if clase in CLASES_RESULTADO or grupo == GRUPO_RESULTADO_EJERCICIO:
            resultado += credito_neto
            continue
        if clase == CLASE_ACTIVO:
            sub = 'activo_corriente' if grupo in GRUPOS_ACTIVO_CORRIENTE else 'activo_no_corriente'
            valor = -credito_neto
        elif clase == CLASE_PASIVO:
            sub = 'pasivo_corriente' if grupo in GRUPOS_PASIVO_CORRIENTE else 'pasivo_no_corriente'
            valor = credito_neto
        elif clase == CLASE_PATRIMONIO:
            sub = 'patrimonio'
            valor = credito_neto
        else:
            continue

        if nivel == GRUPO:
            clave = str(grupo) if grupo else codigo[:2]
        else:
            clave = str(cuenta) if cuenta else codigo
        lineas[sub][clave] += valor
    return {'lineas': lineas, 'resultado': resultado}


def _nombres(saldos, nivel):
    codigos = {
        codigo
        for periodo in saldos.values()
        for cuentas in periodo['lineas'].values()
        for codigo in cuentas
        if codigo.isdigit()
    }
    modelo = ConCuentaGrupo if nivel == GRUPO else ConCuentaCuenta
    return {
        str(id_): nombre
        for id_, nombre in modelo.objects.filter(id__in=[int(c) for c in codigos])
        .values_list('id', 'nombre')
    }


def _nombre_por_defecto(codigo, nivel):
    return f'{"Grupo" if nivel == GRUPO else "Cuenta"} {codigo}'


def _resumen(totales):
    """
    Lo que va en el encabezado de un corte: los totales, si cuadra y las razones.

    `cuadrado` es activo = pasivo + patrimonio, y `diferencia` cuánto le falta
    (activo − pasivo − patrimonio). Si cada asiento cuadra, el estado cuadra;
    lo descuadra un documento con débitos y créditos distintos —los hay, por
    centavos, en datos migrados— o un filtro dinámico (por centro de costo, por
    comprobante). No se redondea: un descuadre de centavos es un dato, no ruido.
    """
    activo = totales['activo']
    pasivo = totales['pasivo']
    corriente = totales['activo_corriente']
    pasivo_corriente = totales['pasivo_corriente']
    return {
        'activo': activo,
        'activo_corriente': corriente,
        'activo_no_corriente': totales['activo_no_corriente'],
        'pasivo': pasivo,
        'pasivo_corriente': pasivo_corriente,
        'pasivo_no_corriente': totales['pasivo_no_corriente'],
        'patrimonio': totales['patrimonio'],
        'pasivo_patrimonio': totales['pasivo_patrimonio'],
        'cuadrado': activo == totales['pasivo_patrimonio'],
        'diferencia': activo - totales['pasivo_patrimonio'],
        'capital_trabajo': corriente - pasivo_corriente,
        'razon_corriente': None if pasivo_corriente == 0 else corriente / pasivo_corriente,
        'endeudamiento': None if activo == 0 else pasivo / activo,
    }


def _prefijo(codigo, largo):
    prefijo = codigo[:largo]
    return int(prefijo) if len(prefijo) == largo and prefijo.isdigit() else None


def _titulo(tipo, nombre):
    return {'tipo': tipo, 'codigo': '', 'nombre': nombre,
            'actual': None, 'anterior': None, 'variacion': None, 'porcentaje': None}


def _fila(tipo, codigo, nombre, actual, anterior):
    if anterior is None:
        variacion = porcentaje = None
    else:
        variacion = actual - anterior
        # Sobre el valor absoluto: una cuenta correctora que se reduce tiene que
        # verse como una disminución, no como un aumento.
        porcentaje = None if anterior == 0 else variacion / abs(anterior)
    return {
        'tipo': tipo,
        'codigo': codigo,
        'nombre': nombre,
        'actual': actual,
        'anterior': anterior,
        'variacion': variacion,
        'porcentaje': porcentaje,
    }
