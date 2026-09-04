import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import NotFound, ValidationError

from general.models import (
    GenDocumento,
    GenDocumentoDetalle,
    GenDocumentoImpuesto,
    GenDocumentoTipo,
    GenFestivo,
    GenItem,
)
from general.servicios.supervigilancia import LiquidadorSupervigilancia
from inventario.models import InvExistencia


def sincronizar_impuestos(detalle, impuestos):
    """Reemplaza los impuestos de un detalle por la lista de GenImpuesto dada."""
    detalle.documentos_impuestos_documento_detalle_rel.all().delete()
    for impuesto in impuestos:
        GenDocumentoImpuesto.objects.create(
            documento_detalle=detalle,
            impuesto=impuesto,
            porcentaje=impuesto.porcentaje,
            porcentaje_base=impuesto.porcentaje_base,
        )


# ---------------------------------------------------- validación de aprobación ----
#
# Aprobar es el punto sin retorno: asigna consecutivo, afecta cartera y deja el
# documento inmutable (`GenDocumento.es_mutable`). Todo lo que no puede pasar de
# ahí se valida antes, en un solo lugar, y siempre levantando `ValidationError`.
#
# Las reglas dependen de la clase o el tipo del documento, así que los ids van en
# constantes con nombre: `documento_clase_id == 100` no le dice nada a nadie.

DOCUMENTO_CLASE_FACTURA_VENTA = 100
DOCUMENTO_CLASE_DOCUMENTO_SOPORTE = 303
DOCUMENTO_CLASE_NOMINA_ELECTRONICA = 702

# Clases que se numeran contra una resolución de la DIAN: el consecutivo tiene que
# caer dentro del rango autorizado y la resolución no puede estar vencida.
DOCUMENTO_CLASES_CON_RESOLUCION = (
    DOCUMENTO_CLASE_FACTURA_VENTA,
    DOCUMENTO_CLASE_DOCUMENTO_SOPORTE,
)

# Tipos cuyo documento tiene que cuadrar antes de aprobarse. Por ahora solo el
# asiento; depreciación y cierre también son partida doble y entran acá el día que
# se confirme que sus documentos actuales cuadran.
DOCUMENTO_TIPOS_PARTIDA_DOBLE = (13,)  # ASIENTO

# Notas crédito: devuelven contra el documento que referencian, y no pueden
# devolver más de lo que ese documento tiene pendiente.
DOCUMENTO_TIPOS_NOTA_CREDITO = (
    2,  # NOTA CRÉDITO DE VENTA
    6,  # NOTA CREDITO COMPRA
)

# Clases que llevan cartera: al aprobarse el documento queda con saldo pendiente
# de cobro o de pago. Son las de venta (100-105) y las de compra (300-304).
DOCUMENTO_CLASES_CON_CARTERA = (
    100, 101, 102, 104, 105,
    300, 301, 302, 303, 304,
)

# Tipos cuya contrapartida contable la define la forma de pago y no el tipo.
DOCUMENTO_TIPOS_CUENTA_DE_FORMA_PAGO = (
    5,   # COMPRA
    11,  # DOCUMENTO SOPORTE
)

# Clases que admiten desaprobación. Las que no están acá se deshacen por otro
# camino (una nota, un ajuste), no quitándoles el aprobado.
DOCUMENTO_CLASES_QUE_PERMITEN_DESAPROBAR = (
    100, 101, 102, 104, 105,  # venta
    200,                      # pago
    300, 301, 303,            # compra
    400,                      # egreso
    500, 501,                 # entrada y salida de almacén
    601, 603,                 # asiento y cierre contable
)

DOCUMENTO_TIPO_REMISION = 29
DOCUMENTO_TIPO_DEVOLUCION_REMISION = 30

# Tipos que mueven remisión en vez de inventario: sacan de disponible sin sacar
# de existencia, porque la mercancía todavía no salió.
DOCUMENTO_TIPOS_REMISION = (
    DOCUMENTO_TIPO_REMISION,
    DOCUMENTO_TIPO_DEVOLUCION_REMISION,
)

# Tipos que recalculan el costo promedio del item: los que meten mercancía y
# traen un precio de entrada contra el cual promediar.
DOCUMENTO_TIPOS_QUE_PROMEDIAN_COSTO = (
    5,  # COMPRA
    9,  # ENTRADA ALMACEN
)

# Tipos cuyos detalles guardan el costo del item al momento de aprobar. Se
# congela acá porque el costo promedio se mueve con cada entrada posterior y el
# margen de esta venta tiene que quedar con el costo que tenía ese día.
DOCUMENTO_TIPOS_QUE_CONGELAN_COSTO = (
    1, 2, 17, 24, 27,  # FACTURA ELECTRÓNICA, NOTA CRÉDITO, CUENTA COBRO, POS ELECTRÓNICO, POS
    5, 6,              # COMPRA, NOTA CREDITO COMPRA
    9, 10,             # ENTRADA ALMACEN, SALIDA ALMACEN
)


def validar_aprobacion(documento, consecutivo):
    """
    Corre todas las reglas de aprobación. Levanta `ValidationError` en la primera
    que falle; si no levanta, el documento se puede aprobar.

    `consecutivo` es el número que va a quedar en el documento —el que ya tiene, o
    el próximo de su tipo—, porque la resolución se valida contra ese número y no
    contra el que tenga la secuencia después.
    """
    _validar_total_no_negativo(documento)
    _validar_partida_doble(documento)
    _validar_resolucion(documento, consecutivo)
    _validar_nomina_electronica(documento)
    _validar_cantidad_afectada(documento)
    _validar_existencias(documento)
    _validar_nota_credito(documento)


def _validar_total_no_negativo(documento):
    if documento.total < 0:
        raise ValidationError('El total del documento no puede ser menor a cero.')


def _validar_resolucion(documento, consecutivo):
    """
    Una factura de venta o un documento soporte se numeran contra una resolución.

    Se valida al aprobar y no al crear porque es acá donde el documento toma su
    consecutivo: antes no hay número que comparar contra el rango.
    """
    if documento.documento_tipo.documento_clase_id not in DOCUMENTO_CLASES_CON_RESOLUCION:
        return

    if not documento.documentos_detalles_documento_rel.exists():
        raise ValidationError('El documento no tiene detalles.')

    resolucion = documento.resolucion
    if resolucion is None:
        return

    if resolucion.fecha_hasta <= date.today():
        raise ValidationError('La fecha de la resolución está vencida.')

    if not (resolucion.consecutivo_desde <= consecutivo <= resolucion.consecutivo_hasta):
        raise ValidationError(
            f'El consecutivo {consecutivo} no corresponde con la resolución, que va '
            f'desde {resolucion.consecutivo_desde} hasta {resolucion.consecutivo_hasta}.'
        )


def _validar_nomina_electronica(documento):
    """La DIAN exige el nombre y el apellido del empleado por separado."""
    if documento.documento_tipo.documento_clase_id != DOCUMENTO_CLASE_NOMINA_ELECTRONICA:
        return

    contacto = documento.contacto
    if contacto is None or not contacto.nombre1 or not contacto.apellido1:
        raise ValidationError('El contacto no tiene nombre1 o apellido1.')


def _validar_cantidad_afectada(documento):
    """
    Una línea que afecta a otra no puede traer más cantidad de la que esa otra
    tiene.

    Se agrupa por detalle afectado en una sola consulta: varias líneas del mismo
    documento pueden apuntar al mismo detalle y lo que se compara es la suma.
    """
    excedidos = (
        documento.documentos_detalles_documento_rel
        .filter(documento_detalle_afectado__isnull=False)
        .values('documento_detalle_afectado_id', 'documento_detalle_afectado__cantidad')
        .annotate(cantidad_total=Sum('cantidad'))
    )
    for fila in excedidos:
        if fila['cantidad_total'] > fila['documento_detalle_afectado__cantidad']:
            raise ValidationError(
                f"No se pueden afectar {fila['cantidad_total']} unidades del detalle "
                f"{fila['documento_detalle_afectado_id']}, que tiene "
                f"{fila['documento_detalle_afectado__cantidad']}."
            )


def _validar_nota_credito(documento):
    """
    Una nota crédito no puede devolver más de lo que el documento referenciado
    debe todavía.

    Se compara contra `GenDocumento.pendiente` del referenciado, que es el mismo
    campo que `_asignar_cartera` llena al aprobarlo: validar por un lado y
    aplicar por otro es como se desincronizan estas dos mitades.
    """
    if documento.documento_referencia_id is None:
        return
    if documento.documento_tipo_id not in DOCUMENTO_TIPOS_NOTA_CREDITO:
        return

    # El pago ya cobrado de la factura vuelve por la nota, así que no cuenta
    # contra el pendiente.
    afectar = documento.total - documento.pago
    pendiente = documento.documento_referencia.pendiente
    if pendiente < afectar:
        raise ValidationError(
            f'El documento referencia tiene {pendiente} pendiente y la nota crédito '
            f'intenta afectar {afectar}.'
        )


def _validar_existencias(documento, signo=1):
    """
    Un item que no admite negativos no puede quedar en rojo.

    `signo` dice en qué sentido se va a mover el documento: 1 al aprobar y -1 al
    desaprobar. Cambia por completo qué líneas hay que mirar. Al aprobar
    preocupan las salidas; al desaprobar preocupan las entradas, porque deshacer
    una entrada saca mercancía que quizá ya se vendió.

    Se revisan dos saldos distintos: `existencia` para lo que mueve inventario y
    `disponible` para lo que mueve remisión. Una salida puede caber en uno y no
    en el otro.
    """
    _validar_saldo_inventario(documento, 'operacion_inventario', 'existencia', 'existente', signo)
    _validar_saldo_inventario(documento, 'operacion_remision', 'disponible', 'disponible', signo)


def _validar_saldo_inventario(documento, campo_operacion, campo_saldo, etiqueta, signo):
    """
    `campo_operacion` acota qué líneas mueven ese saldo y `campo_saldo` cuál de
    los tres de `InvExistencia` tiene que alcanzar.

    Se agrupa por (item, almacén) en una consulta: varias líneas del mismo
    documento pueden mover el mismo item y lo que importa es la suma.
    """
    movimientos = (
        documento.documentos_detalles_documento_rel
        .filter(item__negativo=False, almacen__isnull=False)
        .exclude(**{campo_operacion: 0})
        .values('item_id', 'almacen_id')
        .annotate(cantidad_total=Sum('cantidad_operada'))
    )
    # `cantidad_operada` ya viene con signo, así que el efecto es la suma por el
    # sentido del movimiento. Lo que suma no puede dejar nada en rojo.
    restas = [m for m in movimientos if m['cantidad_total'] * signo < 0]
    if not restas:
        return

    saldos = {
        (e.item_id, e.almacen_id): e
        for e in InvExistencia.objects.filter(
            item_id__in={m['item_id'] for m in restas},
            almacen_id__in={m['almacen_id'] for m in restas},
        )
    }
    for movimiento in restas:
        existencia = saldos.get((movimiento['item_id'], movimiento['almacen_id']))
        if existencia is None:
            raise ValidationError(
                f"El item {movimiento['item_id']} no tiene existencias en el almacén "
                f"{movimiento['almacen_id']}."
            )
        saldo = getattr(existencia, campo_saldo)
        if saldo + movimiento['cantidad_total'] * signo < 0:
            raise ValidationError(
                f"El item {movimiento['item_id']} en el almacén "
                f"{movimiento['almacen_id']} supera la cantidad {etiqueta} {saldo}."
            )


def _validar_partida_doble(documento):
    """
    Un asiento descuadrado no se aprueba.

    La suma va sobre `precio`, no sobre `total`: en una línea contable el valor
    del apunte vive en `precio` y el lado en `naturaleza`, y los derivados quedan
    en cero a propósito (ver `GenDocumentoDetalle.calcular`).
    """
    if documento.documento_tipo_id not in DOCUMENTO_TIPOS_PARTIDA_DOBLE:
        return

    por_lado = {
        fila['naturaleza']: fila['valor'] or Decimal('0')
        for fila in documento.documentos_detalles_documento_rel
        .values('naturaleza')
        .annotate(valor=Sum('precio'))
    }
    debitos = por_lado.get('D', Decimal('0'))
    creditos = por_lado.get('C', Decimal('0'))
    if debitos != creditos:
        raise ValidationError(
            f'El asiento no cuadra: débitos {debitos:,.2f} contra créditos '
            f'{creditos:,.2f} (diferencia {debitos - creditos:,.2f}).'
        )


# ------------------------------------------------------ efectos de aprobar ----
#
# Cada uno deja el documento en memoria y devuelve los campos que tocó, para que
# `aprobar` haga un solo `save(update_fields=...)` al final.

def _asignar_cartera(documento):
    """
    Una factura o una compra nacen a crédito: al aprobarse quedan con saldo.

    Este es el único punto del proyecto donde se escribe `GenDocumento.pendiente`.
    """
    if documento.documento_tipo.documento_clase_id not in DOCUMENTO_CLASES_CON_CARTERA:
        return []
    documento.pendiente = documento.total - documento.pago
    return ['pendiente']


def _asignar_cuenta_de_forma_pago(documento):
    """
    En una compra la contrapartida sale de cómo se pagó (caja, banco, crédito),
    que es un dato del documento, no de su tipo.
    """
    if documento.documento_tipo_id not in DOCUMENTO_TIPOS_CUENTA_DE_FORMA_PAGO:
        return []
    if documento.forma_pago_id is None:
        return []
    documento.cuenta_id = documento.forma_pago.cuenta_id
    return ['cuenta']


def _afectar_documento_referencia(documento, signo=1):
    """
    Una nota crédito descarga el saldo del documento que referencia.

    `signo` invierte el efecto para `desaprobar`: aprobar y desaprobar tienen que
    dejar los saldos como estaban, o el documento arrastra cartera fantasma.

    El referenciado se bloquea porque su pendiente lo pueden estar moviendo otra
    nota o un pago al mismo tiempo.
    """
    if documento.documento_referencia_id is None:
        return []
    if documento.documento_tipo_id not in DOCUMENTO_TIPOS_NOTA_CREDITO:
        return []

    afectar = (documento.total - documento.pago) * signo

    referencia = GenDocumento.objects.select_for_update().get(
        pk=documento.documento_referencia_id
    )
    referencia.afectado += afectar
    referencia.pendiente = referencia.total - (referencia.afectado + referencia.pago)
    referencia.save(update_fields=['afectado', 'pendiente'])

    documento.afectado += afectar
    documento.pendiente -= afectar
    return ['afectado', 'pendiente']


def aprobar(documento_id):
    """Aprueba un documento: valida estado, asigna consecutivo si falta y marca aprobado."""
    with transaction.atomic():
        # Trae el documento bloqueando la fila para evitar aprobaciones concurrentes.
        try:
            documento = GenDocumento.objects.select_for_update().get(pk=documento_id)
        except GenDocumento.DoesNotExist:
            raise NotFound('Documento no encontrado.')

        # No se puede aprobar un documento anulado ni uno ya aprobado.
        if documento.estado_anulado:
            raise ValidationError('El documento está anulado.')
        if documento.estado_aprobado:
            raise ValidationError('El documento ya está aprobado.')

        # El número que va a quedar: el que ya tiene, o el próximo de su tipo. Se
        # averigua antes de validar porque la resolución se valida contra él, y se
        # asigna después porque una validación que falla no debe gastar consecutivo.
        campos_actualizar = ['estado_aprobado']
        documento_tipo = None
        if documento.numero is None:
            documento_tipo = GenDocumentoTipo.objects.select_for_update().get(
                pk=documento.documento_tipo_id
            )
            consecutivo = documento_tipo.consecutivo
        else:
            consecutivo = documento.numero

        validar_aprobacion(documento, consecutivo)

        if documento_tipo is not None:
            documento.numero = consecutivo
            documento_tipo.consecutivo += 1
            documento_tipo.save(update_fields=['consecutivo'])
            campos_actualizar.append('numero')

        # Recorre los detalles y agrupa por detalle afectado cuánto se va a afectar.
        # Bloquea cada detalle afectado para que su pendiente no cambie entre validar y aplicar.
        afectados, totales_a_afectar, cantidades_a_afectar = _agrupar_afectados(documento)

        # Valida primero todo: si algún afectado se sobrepasa de su pendiente, corta sin aplicar nada.
        for afectado_id, total_a_afectar in totales_a_afectar.items():
            afectado = afectados[afectado_id]
            if total_a_afectar > afectado.pendiente:
                raise ValidationError(
                    f'El detalle {afectado_id} solo tiene {afectado.pendiente} pendiente '
                    f'por afectar y se intentan afectar {total_a_afectar}.'
                )

        # Validación superada: suma lo afectado a cada detalle afectado. La plata va en
        # `afectado` (el save recalcula `pendiente`) y las unidades en `cantidad_afectada`,
        # que es lo que mira una remisión para saber cuánto le queda por despachar.
        _aplicar_afectacion(afectados, totales_a_afectar, cantidades_a_afectar, signo=1)

        _afectar_inventario(documento, signo=1)

        campos_actualizar += _asignar_cartera(documento)
        campos_actualizar += _asignar_cuenta_de_forma_pago(documento)
        campos_actualizar += _afectar_documento_referencia(documento)

        # Marca el documento como aprobado (y guarda el número si se asignó arriba).
        documento.estado_aprobado = True
        documento.save(update_fields=campos_actualizar)
    return documento


def _agrupar_afectados(documento):
    """
    Agrupa por detalle afectado la plata y las unidades que este documento le
    aplica, bloqueando cada afectado para que su pendiente no cambie entre
    validar y aplicar.

    Varias líneas del mismo documento pueden apuntar al mismo detalle, así que lo
    que cuenta es la suma y no cada línea por separado.
    """
    afectados = {}
    totales = {}
    cantidades = {}
    for detalle in documento.documentos_detalles_documento_rel.all():
        afectado_id = detalle.documento_detalle_afectado_id
        if afectado_id is None:
            continue
        if afectado_id not in afectados:
            afectados[afectado_id] = GenDocumentoDetalle.objects.select_for_update().get(
                pk=afectado_id
            )
            totales[afectado_id] = Decimal('0')
            cantidades[afectado_id] = Decimal('0')
        totales[afectado_id] += detalle.total
        cantidades[afectado_id] += detalle.cantidad
    return afectados, totales, cantidades


def _aplicar_afectacion(afectados, totales, cantidades, signo):
    """Aplica (signo=1) o revierte (signo=-1) la afectación sobre los detalles."""
    for afectado_id, afectado in afectados.items():
        afectado.afectado += totales[afectado_id] * signo
        afectado.cantidad_afectada += cantidades[afectado_id] * signo
        afectado.cantidad_pendiente -= cantidades[afectado_id] * signo
        afectado.save(update_fields=['afectado', 'cantidad_afectada', 'cantidad_pendiente'])


def desaprobar(documento_id):
    """Desaprueba un documento: valida estado y quita el aprobado (conserva el número)."""
    with transaction.atomic():
        try:
            documento = GenDocumento.objects.select_for_update().get(pk=documento_id)
        except GenDocumento.DoesNotExist:
            raise NotFound('Documento no encontrado.')
        if not documento.estado_aprobado:
            raise ValidationError('El documento no está aprobado.')
        if documento.estado_anulado:
            raise ValidationError('El documento está anulado.')
        if documento.estado_contabilizado:
            raise ValidationError('El documento está contabilizado.')
        if documento.estado_electronico_enviado:
            raise ValidationError('El documento ya fue enviado electrónicamente.')
        if (documento.documento_tipo.documento_clase_id
                not in DOCUMENTO_CLASES_QUE_PERMITEN_DESAPROBAR):
            raise ValidationError('El documento no permite desaprobación.')

        # Deshacer una entrada saca mercancía que quizá ya se despachó: se valida
        # antes de mover nada.
        _validar_existencias(documento, signo=-1)

        # Revierte exactamente lo que hizo `aprobar`: si algo queda sin deshacer, el
        # documento arrastra cartera o unidades afectadas que ya no corresponden.
        afectados, totales_a_afectar, cantidades_a_afectar = _agrupar_afectados(documento)
        _aplicar_afectacion(afectados, totales_a_afectar, cantidades_a_afectar, signo=-1)
        _afectar_inventario(documento, signo=-1)

        campos_actualizar = ['estado_aprobado']
        campos_actualizar += _afectar_documento_referencia(documento, signo=-1)
        campos_actualizar += _quitar_cartera(documento)

        # Quita el estado aprobado (conserva el número ya asignado).
        documento.estado_aprobado = False
        documento.save(update_fields=campos_actualizar)
    return documento


def _afectar_inventario(documento, signo):
    """
    Mueve los saldos de inventario del documento: `InvExistencia` por almacén y
    los acumulados del propio `GenItem`.

    `signo` invierte el movimiento para `desaprobar`. Lo que NO se revierte es el
    costo promedio: es un promedio ponderado y no tiene inversa —al desaprobar no
    se sabe con qué existencia se promedió—, así que desaprobar una compra deja
    el costo donde quedó. Es una limitación conocida, no un olvido.

    `cantidad_operada` ya trae el signo del movimiento (negativo si sale), así que
    acá siempre se suma.
    """
    detalles = list(
        documento.documentos_detalles_documento_rel
        .filter(almacen__isnull=False, item__isnull=False)
        .select_related('documento_detalle_afectado__documento')
    )
    if not detalles:
        return

    es_remision = documento.documento_tipo_id in DOCUMENTO_TIPOS_REMISION
    # El costo solo se toca al aprobar. Al revertir no se recalcula el promedio
    # —es ponderado y no tiene inversa si hubo movimientos en el medio— ni se
    # vuelve a congelar el costo del detalle, que ya quedó con el de ese día.
    aprueba = signo == 1
    promedia_costo = aprueba and documento.documento_tipo_id in DOCUMENTO_TIPOS_QUE_PROMEDIAN_COSTO
    congela_costo = aprueba and documento.documento_tipo_id in DOCUMENTO_TIPOS_QUE_CONGELAN_COSTO

    for detalle in detalles:
        if es_remision:
            _mover_remision(detalle, signo)
            continue
        if detalle.operacion_inventario == 0:
            continue
        _mover_inventario(detalle, signo, promedia_costo, congela_costo)


def _saldo_bloqueado(detalle):
    """
    El saldo de (item, almacén), bloqueado y creado si no existe.

    Se bloquea porque dos aprobaciones del mismo item corren en paralelo y ambas
    leerían el mismo saldo antes de escribirlo.
    """
    existencia, _ = InvExistencia.objects.get_or_create(
        item_id=detalle.item_id, almacen_id=detalle.almacen_id,
    )
    return InvExistencia.objects.select_for_update().get(pk=existencia.pk)


def _mover_inventario(detalle, signo, promedia_costo, congela_costo):
    """
    Una salida que descarga una remisión ya despachada no vuelve a tocar
    `disponible`: esa cantidad salió de disponible cuando se hizo la remisión.
    """
    cantidad = detalle.cantidad_operada * signo
    afectado = detalle.documento_detalle_afectado
    descarga_remision = (
        afectado is not None
        and afectado.documento.documento_tipo_id == DOCUMENTO_TIPO_REMISION
    )

    existencia = _saldo_bloqueado(detalle)
    existencia.existencia += cantidad
    if descarga_remision:
        existencia.remision += cantidad
    else:
        existencia.disponible += cantidad
    existencia.save(update_fields=['existencia', 'remision', 'disponible'])

    item = GenItem.objects.select_for_update().get(pk=detalle.item_id)
    existencia_anterior = item.existencia
    costo_promedio_anterior = item.costo_promedio

    item.existencia += cantidad
    if descarga_remision:
        item.remision += cantidad
    else:
        item.disponible += cantidad

    campos_item = ['existencia', 'remision', 'disponible']
    if promedia_costo:
        promedio = _costo_promedio(
            existencia_anterior, costo_promedio_anterior, cantidad, detalle.precio,
            item.existencia,
        )
        if promedio is not None:
            item.costo_promedio = promedio
        item.costo_total = item.costo_promedio * item.existencia
        campos_item += ['costo_promedio', 'costo_total']
    item.save(update_fields=campos_item)

    if congela_costo:
        detalle.costo = item.costo_promedio
        detalle.save(update_fields=['costo'])


def _costo_promedio(existencia_anterior, costo_anterior, cantidad, precio, existencia):
    """
    Promedio ponderado entre lo que había y lo que entra.

    Con existencia final en cero o negativa no se promedia: dividir por ahí da un
    costo sin sentido, y el anterior es la mejor aproximación que queda.
    """
    if existencia <= 0:
        return None
    return (
        (existencia_anterior * costo_anterior) + (cantidad * precio)
    ) / existencia


def _mover_remision(detalle, signo):
    """
    Una remisión compromete mercancía sin sacarla: sube `remision` y baja
    `disponible`, y `existencia` no se toca hasta que se facture.
    """
    existencia = _saldo_bloqueado(detalle)
    existencia.remision += detalle.cantidad * signo
    existencia.disponible += detalle.cantidad_operada * signo
    existencia.save(update_fields=['remision', 'disponible'])

    item = GenItem.objects.select_for_update().get(pk=detalle.item_id)
    item.remision += detalle.cantidad * signo
    item.disponible += detalle.cantidad_operada * signo
    item.save(update_fields=['remision', 'disponible'])


def _quitar_cartera(documento):
    """Un documento sin aprobar no debe cobrarse: deja de tener saldo pendiente."""
    if documento.documento_tipo.documento_clase_id not in DOCUMENTO_CLASES_CON_CARTERA:
        return []
    documento.pendiente = Decimal('0')
    return ['pendiente']


def generar(documento_tipo_origen, documento_tipo_destino_id, anio, mes, documento_ids=None):
    # Ventana del periodo: los detalles generados viven dentro de este mes.
    primer_dia = date(anio, mes, 1)
    fecha = date(anio, mes, calendar.monthrange(anio, mes)[1])
    fecha_origen = date(anio + mes // 12, mes % 12 + 1, 1)

    def acotar_al_periodo(detalle):
        """
        Recorta `[fecha_desde, fecha_hasta]` del detalle origen a la ventana del mes.

        Retorna `None` si el rango no se solapa con el periodo (el detalle no se
        genera). Aborta si al detalle le falta alguna de las dos fechas.
        """
        if detalle.fecha_desde is None or detalle.fecha_hasta is None:
            raise ValidationError({
                'detail': (
                    f'El detalle {detalle.id} del documento {detalle.documento_id} '
                    f'no tiene fecha desde y fecha hasta.'
                )
            })
        if detalle.fecha_desde > fecha or detalle.fecha_hasta < primer_dia:
            return None
        return (
            max(detalle.fecha_desde, primer_dia),
            min(detalle.fecha_hasta, fecha),
        )

    festivos = set(
        GenFestivo.objects
        .filter(fecha__range=(primer_dia, fecha))
        .values_list('fecha', flat=True)
    )

    def calcular_horas(detalle, fecha_desde, fecha_hasta):
        """
        Recalcula horas/diurnas/nocturnas y días del detalle para su rango acotado,
        contando día a día el calendario real del periodo.

        Un día cuenta si es festivo y el detalle marca `festivo`, o si no es festivo
        y su día de la semana está marcado. En un festivo manda el flag `festivo`:
        un lunes festivo con `festivo=False` no cuenta aunque `lunes` esté marcado.
        """
        if detalle.hora_desde is None or detalle.hora_hasta is None:
            raise ValidationError({
                'detail': (
                    f'El detalle {detalle.id} del documento {detalle.documento_id} '
                    f'no tiene hora desde y hora hasta.'
                )
            })

        diurnas_dia, nocturnas_dia = LiquidadorSupervigilancia.particionar_horas(
            detalle.hora_desde, detalle.hora_hasta,
        )
        # Indexado por date.weekday(): 0=lunes ... 6=domingo.
        dias_semana = (
            detalle.lunes, detalle.martes, detalle.miercoles, detalle.jueves,
            detalle.viernes, detalle.sabado, detalle.domingo,
        )

        dias = 0
        dia = fecha_desde
        while dia <= fecha_hasta:
            if dia in festivos:
                aplica = detalle.festivo
            else:
                aplica = dias_semana[dia.weekday()]
            if aplica:
                dias += 1
            dia += timedelta(days=1)

        centavos = Decimal('0.01')
        horas_diurnas = (diurnas_dia * dias).quantize(centavos)
        horas_nocturnas = (nocturnas_dia * dias).quantize(centavos)
        return {
            'dias': dias,
            'horas': horas_diurnas + horas_nocturnas,
            'horas_diurnas': horas_diurnas,
            'horas_nocturnas': horas_nocturnas,
        }

    def clonar(instancia, excluir, overrides):
        """Construye una copia sin guardar, omitiendo `excluir` y aplicando `overrides`."""
        datos = {
            campo.attname: getattr(instancia, campo.attname)
            for campo in instancia._meta.concrete_fields
            if not campo.primary_key and campo.name not in excluir
        }
        datos.update(overrides)
        return type(instancia)(**datos)

    excluir_documento = {
        'id', 'numero', 'fecha', 'fecha_validacion',
        'documento_tipo', 'documento_referencia',
        'cue', 'qr', 'referencia_cue', 'referencia_numero', 'referencia_prefijo',
        'electronico_id',
        'evento_documento', 'evento_recepcion', 'evento_aceptacion',
        'estado_aprobado', 'estado_anulado', 'estado_contabilizado',
        'estado_electronico', 'estado_electronico_enviado',
        'estado_electronico_notificado', 'estado_electronico_evento',
        'estado_electronico_descartado',
    }
    excluir_detalle = {'id', 'documento', 'documento_detalle_afectado'}
    excluir_impuesto = {'id', 'documento_detalle'}

    qs = GenDocumento.objects.filter(
        documento_tipo=documento_tipo_origen,
        fecha__lte=fecha,
    )
    if documento_ids:
        qs = qs.filter(id__in=documento_ids)
    qs = qs.prefetch_related(
        'documentos_detalles_documento_rel__documentos_impuestos_documento_detalle_rel',
    )
    documentos = list(qs)

    if not documentos:
        raise ValidationError({'detail': 'No hay documentos para generar.'})

    generados = []
    with transaction.atomic():
        for origen in documentos:
            # Solo los detalles cuyo rango se solapa con el periodo, ya acotados a él.
            detalles = []
            for detalle in origen.documentos_detalles_documento_rel.all():
                rango = acotar_al_periodo(detalle)
                if rango is not None:
                    detalles.append((detalle, rango))

            # Sin detalles vigentes en el periodo no se genera el documento.
            if not detalles:
                continue

            nuevo = clonar(origen, excluir_documento, {
                'documento_tipo_id': documento_tipo_destino_id,
                'fecha': fecha,
                'documento_referencia_id': origen.id,
            })
            nuevo.save()
            for detalle, (fecha_desde, fecha_hasta) in detalles:
                nuevo_detalle = clonar(detalle, excluir_detalle, {
                    'documento_id': nuevo.id,
                    'documento_detalle_afectado_id': detalle.id,
                    'fecha_desde': fecha_desde,
                    'fecha_hasta': fecha_hasta,
                    **calcular_horas(detalle, fecha_desde, fecha_hasta),
                })
                nuevo_detalle.save()
                for impuesto in detalle.documentos_impuestos_documento_detalle_rel.all():
                    clonar(impuesto, excluir_impuesto, {
                        'documento_detalle_id': nuevo_detalle.id,
                    }).save()
            nuevo.recalcular_totales()
            nuevo.save()

            origen.fecha = fecha_origen
            origen.save(update_fields=['fecha'])

            generados.append(nuevo)

    if not generados:
        raise ValidationError(
            {'detail': 'Ningún documento tiene detalles vigentes en el periodo.'}
        )

    return generados
