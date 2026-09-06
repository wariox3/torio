"""
Balance de prueba: el plan de cuentas con el movimiento de un rango, jerarquizado.

Cinco informes salen de acá y comparten casi todo — los dos balances y los tres
auxiliares. Lo único que cambia entre ellos es por qué campos agrupa el barrido
de `con_movimiento` y qué filas de detalle cuelgan de cada auxiliar; la
jerarquía, la aritmética y el orden son los mismos, y así tienen que seguir
siendo. Esas dos variaciones se declaran, no se programan: la primera con la
función de agrupado, la segunda con una de las constantes de `Detalle`.
"""
from collections import defaultdict, namedtuple
from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from contabilidad.models import ConCuenta, ConMovimiento

# Whitelist de filtros dinámicos del informe. Se aplican sobre `con_movimiento`,
# antes de agrupar, así que acotan por igual el saldo anterior y el movimiento
# del rango. `fecha` no está a propósito: el rango del balance la gobierna, y un
# filtro por fecha encima del rango daría dos cortes distintos.
CAMPOS_FILTRABLES = {
    'cuenta_id',
    'cuenta__codigo',
    'cuenta__nombre',
    'centro_costo_id',
    'contacto_id',
    'comprobante_id',
    'documento_id',
    'periodo_id',
    'numero',
    'naturaleza',
    'cierre',
    'saldo_inicial',
    'base',
    'detalle',
}

# Un asiento de cierre no es movimiento del periodo: cancela las cuentas de
# resultado contra el ejercicio. Entra al saldo anterior —el saldo con el que la
# cuenta llega al rango es el que quedó después del cierre— pero no a las
# columnas de débito y crédito del rango ni al detalle de los auxiliares, porque
# ahí duplicaría el resultado del año en la columna de diciembre.
# Los informes planos no lo excluyen: son listas de lo que pasó, no un corte.
_SIN_CIERRE = Q(cierre=False)

_CERO = Decimal('0')
_CERO_SQL = Value(_CERO, output_field=DecimalField(max_digits=20, decimal_places=6))

# Columnas de importe de cada fila del informe, en el orden en que se presentan.
COLUMNAS = ('saldo_anterior', 'debito', 'credito', 'saldo_final')

# Los niveles que agrupan el plan, del más general al más específico, con el FK
# de `ConCuenta` que apunta a cada catálogo. Un nivel en NULL se salta: hoy
# `cuenta_subcuenta` lo está en todas las cuentas, así que el informe sale con
# tres niveles de subtotal, pero el día que se pueble aparece solo.
NIVELES = (
    ('CLASE', 'cuenta_clase'),
    ('GRUPO', 'cuenta_grupo'),
    ('CUENTA', 'cuenta_cuenta'),
    ('SUBCUENTA', 'cuenta_subcuenta'),
)

# Tipo de las filas que sí son una cuenta del plan. Por encima están los
# subtotales de `NIVELES`; por debajo, el detalle —terceros y movimientos—, que
# no suma en `totalizar` porque ya está dentro de su auxiliar.
HOJA = 'AUXILIAR'
TERCERO = 'TERCERO'
MOVIMIENTO = 'MOVIMIENTO'

# Los informes planos no tienen jerarquía, pero sus filas también se etiquetan:
# es lo que deja que `totalizar` y el front traten a todas igual.
RETENCION = 'RETENCION'
RESULTADO = 'RESULTADO'

# Orden de desempate entre las filas de jerarquía que comparten código: primero
# los subtotales, de arriba abajo, y después la cuenta. El detalle no entra acá:
# va pegado a su hoja, en el orden en que lo armó `_detallar`.
_ORDEN_TIPO = {tipo: indice for indice, (tipo, _) in enumerate(NIVELES)}
_ORDEN_TIPO[HOJA] = len(NIVELES)

# Columnas que solo llena el detalle. Van en None en las demás filas para que
# todos los informes puedan leer cualquier fila sin preguntar de qué tipo es.
_COLUMNAS_DETALLE = (
    'contacto_id', 'identificacion', 'contacto',
    'movimiento_id', 'comprobante', 'numero', 'fecha', 'detalle', 'base',
)

# Qué cuelga de cada auxiliar. `anidado` solo tiene sentido con las dos en True:
# distingue los movimientos metidos bajo su tercero de los que van sueltos al
# final de la cuenta.
Detalle = namedtuple('Detalle', 'terceros movimientos anidado')

SIN_DETALLE = Detalle(terceros=False, movimientos=False, anidado=False)
POR_TERCERO = Detalle(terceros=True, movimientos=False, anidado=False)
POR_MOVIMIENTO = Detalle(terceros=False, movimientos=True, anidado=False)
POR_TERCERO_ANIDADO = Detalle(terceros=True, movimientos=True, anidado=True)
POR_TERCERO_Y_MOVIMIENTO = Detalle(terceros=True, movimientos=True, anidado=False)


def balance_prueba(fecha_desde, fecha_hasta):
    """
    Movimiento agrupado por cuenta: el del rango y el acumulado previo.

    Devuelve los importes crudos por cuenta (`anterior_debito`,
    `anterior_credito`, `movimiento_debito`, `movimiento_credito`). Las filas que
    ve el usuario las arma `jerarquizar`, que es quien cruza esto contra el plan
    de cuentas: acá solo aparecen las cuentas que tienen movimiento.
    """
    return _agrupar(fecha_desde, fecha_hasta)


def balance_prueba_contacto(fecha_desde, fecha_hasta):
    """
    Lo mismo abierto por tercero: un agregado por cada par cuenta/contacto.

    El grupo del contacto en NULL también viene, y tiene que venir: el auxiliar
    se arma sumando todos los grupos de la cuenta, así que si se filtrara acá el
    total de la cuenta perdería lo que se movió sin tercero. Lo que no genera es
    fila de detalle — eso lo decide `jerarquizar_contacto`.

    La identificación y el nombre entran al `values` en vez de resolverse en una
    segunda consulta: son 1 a 1 con el contacto, así que no parten ningún grupo.
    """
    return _agrupar(
        fecha_desde, fecha_hasta,
        'contacto_id', 'contacto__numero_identificacion', 'contacto__nombre_corto',
    )


def movimientos(fecha_desde, fecha_hasta):
    """
    Los movimientos del rango, uno por fila, para el detalle de los auxiliares.

    Es la segunda consulta del informe y no se puede evitar: los agregados dicen
    cuánto movió cada cuenta, no qué lo movió. Va ordenada como se lee un libro
    auxiliar —por fecha, y dentro del día por número de asiento—, con el id de
    desempate para que dos asientos del mismo número no salgan hoy en un orden y
    mañana en otro.

    Deja fuera los asientos de cierre, igual que los agregados: el detalle tiene
    que explicar las columnas de débito y crédito del auxiliar, y un movimiento
    que no está en ellas no las explica.

    Lleva los mismos filtros dinámicos que los agregados, así que un informe
    filtrado por centro de costo acota las dos mitades por igual.
    """
    return _movimientos(fecha_desde, fecha_hasta).filter(_SIN_CIERRE)


def _movimientos(fecha_desde, fecha_hasta):
    return (
        ConMovimiento.objects
        .filter(fecha__gte=fecha_desde, fecha__lte=fecha_hasta)
        .select_related('comprobante', 'contacto')
        .order_by('fecha', 'numero', 'id')
    )


def movimientos_con_base(fecha_desde, fecha_hasta):
    """
    Los movimientos del rango sobre cuentas que exigen base.

    Filtra por `cuenta.exige_base` y no por `base != 0`: la que decide es la
    configuración de la cuenta, no el importe. Un movimiento a una cuenta de
    retención al que se le olvidó la base tiene que salir —en cero, para que se
    vea que falta—, y una base cargada por error en una cuenta que no la exige no
    tiene por qué aparecer en el informe de bases.

    A diferencia del detalle de los auxiliares, los asientos de cierre entran:
    esto no es un corte del periodo sino la lista de lo que se movió con base.
    """
    return (
        _movimientos(fecha_desde, fecha_hasta)
        .filter(cuenta__exige_base=True)
        .select_related('cuenta')
        .order_by('cuenta__codigo', 'fecha', 'numero', 'id')
    )


def filas_movimiento(movimiento):
    """
    Filas de un informe plano: una por movimiento, sin jerarquía ni subtotales.

    El informe de bases no se lee contra el plan de cuentas sino contra lo que
    pasó, así que acá no hay nada que jerarquizar: las cuentas sin movimiento no
    tienen base que mostrar.
    """
    return [_componer_movimiento(mov.cuenta, mov) for mov in movimiento]


# Primera clase del PUC que es de resultado. De ahí para arriba —ingresos,
# gastos, costos— son las cuentas que se cierran contra el ejercicio; de ahí para
# abajo son de balance y no entran al estado de resultados.
CLASE_RESULTADO = 4


def certificado_retencion(fecha_desde, fecha_hasta):
    """
    Lo retenido a cada tercero en cada cuenta, con el pago que lo causó.

    Son dos netos por grupo, y ninguno de los dos es el saldo de la cuenta:

    - `retenido` es débito menos crédito, lo efectivamente retenido y consignado.
    - `base_retenido` es la base de los movimientos débito menos la de los
      crédito. Se parte por el signo del movimiento y no por el de la base porque
      la base siempre es positiva: lo que dice si suma o resta es si el
      movimiento retuvo o reversó.

    No filtra por cuenta: el certificado se emite sobre las cuentas de retención
    que pida quien lo genera, con los filtros dinámicos del informe.
    """
    return (
        ConMovimiento.objects.filter(fecha__gte=fecha_desde, fecha__lte=fecha_hasta)
        .values(
            'cuenta_id', 'cuenta__codigo', 'cuenta__nombre',
            'contacto_id', 'contacto__numero_identificacion', 'contacto__nombre_corto',
        )
        .annotate(
            retenido_debito=Coalesce(Sum('debito'), _CERO_SQL),
            retenido_credito=Coalesce(Sum('credito'), _CERO_SQL),
            base_debito=Coalesce(Sum('base', filter=Q(debito__gt=0)), _CERO_SQL),
            base_credito=Coalesce(Sum('base', filter=Q(credito__gt=0)), _CERO_SQL),
        )
        .order_by('cuenta__codigo', 'contacto_id')
    )


def filas_certificado(agrupado):
    """Filas del certificado de retención: una por cuenta y tercero."""
    return [
        {
            'tipo': RETENCION,
            'cuenta_id': grupo['cuenta_id'],
            'codigo': grupo['cuenta__codigo'],
            'nombre': grupo['cuenta__nombre'],
            'contacto_id': grupo['contacto_id'],
            'identificacion': grupo['contacto__numero_identificacion'],
            'contacto': grupo['contacto__nombre_corto'],
            'base_retenido': grupo['base_debito'] - grupo['base_credito'],
            'retenido': grupo['retenido_debito'] - grupo['retenido_credito'],
        }
        for grupo in agrupado
    ]


def estado_resultados(fecha_desde, fecha_hasta):
    """
    Ingresos, gastos y costos del rango, por cuenta.

    Solo cuentas de resultado y solo las que movieron: a diferencia del balance,
    este informe no se lee contra el plan sino contra el periodo — una cuenta de
    gasto que no movió no es una línea del estado de resultados.

    No arrastra saldo anterior por la misma razón: el resultado es del periodo,
    no acumulado desde el principio de la historia.
    """
    return _por_cuenta_del_periodo(fecha_desde, fecha_hasta, CLASE_RESULTADO)


def estado_situacion_financiera(fecha_desde, fecha_hasta):
    """
    El mismo corte por cuenta, sin acotar la clase.

    Es la consulta del estado de resultados sin el piso de clase, tal como sale
    de itrio: por eso el informe termina trayendo también las cuentas de
    resultado, que en un estado de situación financiera no deberían estar.

    Tampoco arrastra saldo anterior, así que lo que muestra es el movimiento del
    rango y no el saldo de la cuenta a la fecha de corte. Para el saldo real está
    el balance de prueba.
    """
    return _por_cuenta_del_periodo(fecha_desde, fecha_hasta)


def _por_cuenta_del_periodo(fecha_desde, fecha_hasta, clase_minima=None):
    """Movimiento del rango agrupado por cuenta, con los nombres de clase y grupo."""
    qs = ConMovimiento.objects.filter(fecha__gte=fecha_desde, fecha__lte=fecha_hasta)
    if clase_minima is not None:
        qs = qs.filter(cuenta__cuenta_clase_id__gte=clase_minima)
    return (
        qs.values(
            'cuenta_id', 'cuenta__codigo', 'cuenta__nombre',
            'cuenta__cuenta_clase_id', 'cuenta__cuenta_clase__nombre',
            'cuenta__cuenta_grupo_id', 'cuenta__cuenta_grupo__nombre',
        )
        .annotate(
            total_debito=Coalesce(Sum('debito'), _CERO_SQL),
            total_credito=Coalesce(Sum('credito'), _CERO_SQL),
        )
        .order_by('cuenta__cuenta_clase_id', 'cuenta__cuenta_grupo_id', 'cuenta__codigo')
    )


def filas_estado(agrupado):
    """
    Filas de los dos estados: una por cuenta, con su clase y su grupo.

    El saldo va invertido respecto del balance (`crédito − débito`) para que el
    ingreso se lea positivo y el gasto negativo, que es como se lee un estado de
    resultados. En el balance el mismo ingreso sale negativo, y las dos cosas son
    correctas: son dos convenciones de presentación, no dos cálculos.
    """
    return [
        {
            'tipo': RESULTADO,
            'cuenta_id': grupo['cuenta_id'],
            'codigo': grupo['cuenta__codigo'],
            'nombre': grupo['cuenta__nombre'],
            'clase': grupo['cuenta__cuenta_clase__nombre'] or '',
            'grupo': grupo['cuenta__cuenta_grupo__nombre'] or '',
            'saldo': grupo['total_credito'] - grupo['total_debito'],
        }
        for grupo in agrupado
    ]


def _agrupar(fecha_desde, fecha_hasta, *campos):
    """
    Un solo barrido de `con_movimiento` para las dos mitades del balance.

    Los `Sum` con `filter` separan lo anterior a `fecha_desde` de lo que cae
    dentro del rango, y el `filter(fecha__lte=fecha_hasta)` de entrada acota el
    scan por arriba.

    El saldo anterior suma desde el primer movimiento de la historia, porque no
    hay saldo guardado en ninguna parte: `con_saldo_cuenta` existe como modelo
    pero nadie la escribe todavía. Cuando se consolide al bloquear el periodo,
    esta función es el único lugar que cambia — los informes, la API y el front
    no se enteran.

    Se devuelve un queryset y no una lista porque la vista todavía tiene que
    aplicarle los filtros dinámicos, que van en el WHERE, antes de agrupar.
    """
    return (
        ConMovimiento.objects.filter(fecha__lte=fecha_hasta)
        .values('cuenta_id', *campos)
        .annotate(
            anterior_debito=Coalesce(Sum('debito', filter=Q(fecha__lt=fecha_desde)), _CERO_SQL),
            anterior_credito=Coalesce(Sum('credito', filter=Q(fecha__lt=fecha_desde)), _CERO_SQL),
            movimiento_debito=Coalesce(
                Sum('debito', filter=Q(fecha__gte=fecha_desde) & _SIN_CIERRE), _CERO_SQL,
            ),
            movimiento_credito=Coalesce(
                Sum('credito', filter=Q(fecha__gte=fecha_desde) & _SIN_CIERRE), _CERO_SQL,
            ),
        )
        # `ConMovimiento.Meta.ordering` es `['-id']`, y sobre un queryset
        # agrupado Django mete el campo de ordenamiento en el GROUP BY: sin
        # vaciarlo, el balance saldría partido en una fila por movimiento.
        .order_by()
    )


def jerarquizar(agrupado, movimiento=(), detalle=SIN_DETALLE, solo_con_saldo=False):
    """
    Filas del informe: una por cuenta del plan, con subtotales y detalle.

    El recorrido lo manda el plan de cuentas, no los movimientos, así que una
    cuenta que nunca movió también sale — en ceros, pero sale, que es lo que hace
    que el informe se lea contra el plan y no contra lo que pasó. Los subtotales
    de clase, grupo y cuenta se calculan sumando las hojas que cuelgan de cada
    uno según sus FK, y nunca el detalle: cada importe está en su hoja y otra vez
    en su tercero y en su movimiento, así que contarlo todo multiplicaría el
    balance.

    `detalle` dice qué cuelga de cada auxiliar y es lo único que separa a los
    cinco informes; `movimiento` solo hace falta cuando el detalle los pide.

    Con `solo_con_saldo` se descartan las hojas que quedan en ceros en las cuatro
    columnas, con su detalle. No altera ningún subtotal —una fila en ceros aporta
    cero—, y un subtotal que se queda sin hojas no llega a existir, porque son
    las hojas las que lo crean.
    """
    por_cuenta = defaultdict(list)
    for fila in agrupado:
        por_cuenta[fila['cuenta_id']].append(fila)

    movimientos_por_cuenta = defaultdict(list)
    for fila in movimiento:
        movimientos_por_cuenta[fila.cuenta_id].append(fila)

    hojas = []
    for cuenta in _plan():
        grupos = por_cuenta.get(cuenta.id, ())
        fila = _componer(cuenta, _sumar(grupos))
        if solo_con_saldo and _en_ceros(fila):
            continue
        hojas.append((cuenta, fila, _detallar(
            cuenta, grupos, movimientos_por_cuenta.get(cuenta.id, ()), detalle, solo_con_saldo,
        )))

    filas = _ordenar_por_codigo(hojas)
    for fila in filas:
        for columna in _COLUMNAS_DETALLE:
            fila.setdefault(columna, None)
    return filas


def _detallar(cuenta, grupos, movimientos_cuenta, detalle, solo_con_saldo):
    """
    Las filas que cuelgan de un auxiliar, en el orden en que se leen.

    Los terceros salen de los agregados y no de los movimientos: así aparece
    también el contacto que movió la cuenta antes del rango y no volvió a
    moverla, que trae saldo anterior y es parte del saldo de la cuenta.

    Los movimientos sin contacto no cuelgan de ningún tercero. En el informe
    anidado eso los deja fuera —el informe es por contacto—; en los otros dos van
    igual, porque ahí la lista es de la cuenta entera. Que una cuenta mezcle
    movimientos con y sin tercero es un error de datos, no un caso a representar.
    """
    if not detalle.terceros and not detalle.movimientos:
        return ()

    terceros = ()
    if detalle.terceros:
        terceros = [
            (grupo['contacto_id'], _componer_tercero(cuenta, grupo))
            for grupo in sorted(
                (grupo for grupo in grupos if grupo['contacto_id'] is not None),
                key=lambda grupo: grupo['contacto_id'],
            )
        ]
        if solo_con_saldo:
            terceros = [par for par in terceros if not _en_ceros(par[1])]

    if not detalle.movimientos:
        return [fila for _, fila in terceros]

    filas_movimiento = [_componer_movimiento(cuenta, mov) for mov in movimientos_cuenta]

    if not detalle.anidado:
        return [fila for _, fila in terceros] + filas_movimiento

    por_contacto = defaultdict(list)
    for fila in filas_movimiento:
        por_contacto[fila['contacto_id']].append(fila)

    anidado = []
    for contacto_id, fila in terceros:
        anidado.append(fila)
        anidado.extend(por_contacto.get(contacto_id, ()))
    return anidado


def totalizar(filas, tipo=HOJA, columnas=COLUMNAS):
    """
    Totales del informe, sumando un solo tipo de fila.

    En los informes jerárquicos se suman los auxiliares y nada más: los
    subtotales y el detalle están hechos de ellos, así que sumarlo todo
    multiplicaría el balance. En un balance cuadrado el total de débitos iguala
    al de créditos y los dos saldos dan cero.

    En un informe plano no hay nada que descontar —todas sus filas están al mismo
    nivel—, así que va con `tipo=None`. Qué se suma y sobre qué filas lo declara
    el serializer de totales de cada informe.
    """
    totales = dict.fromkeys(columnas, _CERO)
    for fila in filas:
        if tipo is not None and fila['tipo'] != tipo:
            continue
        for columna in columnas:
            totales[columna] += fila[columna]
    return totales


def _plan():
    """El plan de cuentas con sus tres catálogos de nivel; sale por código (Meta.ordering)."""
    return ConCuenta.objects.select_related(*(campo for _, campo in NIVELES))


def _componer(cuenta, crudo):
    """
    Traduce los importes crudos de una cuenta a la fila que ve el usuario.

    El saldo va neteado y con signo en una sola columna (`débito − crédito`), no
    partido en dos: un pasivo se lee en negativo, que es como suman los
    subtotales sin tener que volver a interpretar las columnas.
    """
    return {
        'tipo': HOJA,
        'cuenta_id': cuenta.id,
        'codigo': cuenta.codigo,
        'nombre': cuenta.nombre,
        **_importes(crudo),
    }


def _componer_tercero(cuenta, crudo):
    """Fila de detalle: la misma cuenta, con el tercero y sus importes."""
    return {
        'tipo': TERCERO,
        'cuenta_id': cuenta.id,
        'codigo': cuenta.codigo,
        'nombre': cuenta.nombre,
        'contacto_id': crudo['contacto_id'],
        'identificacion': crudo['contacto__numero_identificacion'],
        'contacto': crudo['contacto__nombre_corto'],
        **_importes(crudo),
    }


def _componer_movimiento(cuenta, movimiento):
    """
    Fila de un movimiento suelto.

    Los dos saldos van en cero y no en el neto del movimiento: un movimiento no
    tiene saldo, tiene débito o crédito. Poner ahí un acumulado corrido sería
    otro informe —uno que ya no se puede filtrar ni paginar sin mentir— y
    además rompería el cuadre con el auxiliar de arriba.
    """
    return {
        'tipo': MOVIMIENTO,
        'cuenta_id': cuenta.id,
        'codigo': cuenta.codigo,
        'nombre': cuenta.nombre,
        'contacto_id': movimiento.contacto_id,
        'identificacion': movimiento.contacto and movimiento.contacto.numero_identificacion,
        'contacto': movimiento.contacto and movimiento.contacto.nombre_corto,
        'movimiento_id': movimiento.id,
        'comprobante': movimiento.comprobante.nombre,
        'numero': movimiento.numero,
        'fecha': movimiento.fecha,
        'detalle': movimiento.detalle,
        'base': movimiento.base,
        'saldo_anterior': _CERO,
        'debito': movimiento.debito,
        'credito': movimiento.credito,
        'saldo_final': _CERO,
    }


def _importes(crudo):
    anterior = _CERO
    debito = _CERO
    credito = _CERO
    if crudo is not None:
        anterior = crudo['anterior_debito'] - crudo['anterior_credito']
        debito = crudo['movimiento_debito']
        credito = crudo['movimiento_credito']

    return {
        'saldo_anterior': anterior,
        'debito': debito,
        'credito': credito,
        'saldo_final': anterior + debito - credito,
    }


def _sumar(grupos):
    """Reúne los grupos de una cuenta en un solo agregado crudo, o None si no movió."""
    if not grupos:
        return None
    total = dict.fromkeys(
        ('anterior_debito', 'anterior_credito', 'movimiento_debito', 'movimiento_credito'), _CERO,
    )
    for grupo in grupos:
        for campo in total:
            total[campo] += grupo[campo]
    return total


def _en_ceros(fila):
    return not any(fila[columna] for columna in COLUMNAS)


def _ordenar_por_codigo(hojas):
    """
    Une hojas, subtotales y detalle en una sola lista ordenada por código.

    Ordenar la jerarquía por código como texto —y no emitir cada subtotal justo
    antes de su primera hoja— es lo que hace que un subtotal caiga en su lugar
    aunque el plan tenga una cuenta cuyo FK no concuerda con su código: `4155` va
    antes de `41555005` y `4160` después de `41555095` porque así ordena el
    texto, sin que importe de qué cuenta cuelga cada auxiliar. Con un plan bien
    armado el resultado es el mismo anidamiento de siempre; con uno torcido, el
    informe sigue saliendo legible y ningún importe se pierde.

    El detalle no entra en el ordenamiento: viaja pegado a su hoja y se vuelca
    detrás de ella. Si se ordenara junto al resto habría que inventarle una clave
    a cada nivel de anidamiento, y el movimiento metido bajo su tercero se
    despegaría de él.

    Dos pasadas y no una: el subtotal necesita estar sumado antes de escribirse.
    """
    acumulado = {}
    nombre = {}
    for cuenta, fila, _ in hojas:
        for indice, (_, campo) in enumerate(NIVELES):
            ancestro = getattr(cuenta, f'{campo}_id')
            if ancestro is None:
                continue
            clave = (indice, ancestro)
            nombre[clave] = getattr(cuenta, campo).nombre or ''
            totales = acumulado.setdefault(clave, dict.fromkeys(COLUMNAS, _CERO))
            for columna in COLUMNAS:
                totales[columna] += fila[columna]

    bloques = [
        (
            (str(ancestro), indice),
            [{
                'tipo': NIVELES[indice][0],
                'cuenta_id': None,
                'codigo': str(ancestro),
                'nombre': nombre[(indice, ancestro)],
                **totales,
            }],
        )
        for (indice, ancestro), totales in acumulado.items()
    ]
    bloques.extend(
        ((fila['codigo'], _ORDEN_TIPO[HOJA]), [fila, *detalle])
        for _, fila, detalle in hojas
    )

    return [fila for _, bloque in sorted(bloques, key=lambda par: par[0]) for fila in bloque]
