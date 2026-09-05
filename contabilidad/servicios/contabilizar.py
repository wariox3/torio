"""
Contabilización de documentos: deriva de un documento aprobado los movimientos
contables que lo representan, y los borra al descontabilizar.

El asiento no está guardado en ninguna parte: se deriva del documento cada vez, a
partir de su tipo, sus detalles y sus impuestos. Por eso todo lo que decide una
cuenta o una naturaleza vive en este archivo y no repartido entre serializers.
"""
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from contabilidad.models import ConMovimiento, ConPeriodo
from general.models import GenDocumento, GenDocumentoImpuesto
from seguridad.contexto import obtener_usuario_actual
from humano.models import (
    HumConceptoCuenta,
    HumConfiguracionAporte,
    HumConfiguracionProvision,
)

CERO = Decimal('0')
DEBITO = 'D'
CREDITO = 'C'

# ------------------------------------------------------------- naturaleza ----
#
# El sistema anterior decidía débito o crédito con listas de ids quemadas
# (`documento_tipo_id in [1, 3, 17, 24, 27]`). Esas listas son exactamente el
# signo de `GenDocumentoTipo.operacion`: +1 en el documento que suma (factura,
# compra) y -1 en el que devuelve (nota crédito). Acá se usa el signo, así que un
# tipo de documento nuevo no obliga a volver a tocar este archivo.
#
# Con ese signo, cada movimiento sale de una regla de partida doble:
#
#     cartera por cobrar   +operacion   (la factura debita al cliente)
#     ingreso por venta    -operacion   (la factura acredita el ingreso)
#     cartera por pagar    -operacion   (la compra acredita al proveedor)
#     costo o inventario   +operacion   (la compra debita el gasto)
#
# El impuesto sigue al documento multiplicado por su propia `operacion`, que es
# -1 en las retenciones.

# Tipos con una regla propia que ningún campo del modelo alcanza a expresar.
DOCUMENTO_TIPO_PAGO = 4
DOCUMENTO_TIPO_EGRESO = 8
DOCUMENTO_TIPO_ASIENTO = 13
DOCUMENTO_TIPO_NOMINA = 14
DOCUMENTO_TIPO_PRIMA = 20
DOCUMENTO_TIPO_SEGURIDAD_SOCIAL = 22
DOCUMENTO_TIPO_CIERRE = 25

# Mes 13: el periodo de ajustes y cierre (ver `ConPeriodo.mes`).
MES_CIERRE = 13

# Conceptos de nómina cuyo movimiento se detalla con el empleado en vez del
# nombre del concepto.
CONCEPTO_TIPOS_CON_EMPLEADO = (5, 6)

# Provisiones de nómina: campo del documento -> `tipo` en HumConfiguracionProvision.
PROVISIONES = (
    ('provision_cesantia', 'CESANTIA'),
    ('provision_interes', 'INTERES'),
    ('provision_prima', 'PRIMA'),
    ('provision_vacacion', 'VACACION'),
)

# Cuánto se precarga para armar el asiento sin una query por línea.
_RELACIONES_DOCUMENTO = (
    'documento_tipo', 'documento_tipo__cuenta_cobrar', 'documento_tipo__cuenta_pagar',
    'contacto', 'sede', 'forma_pago__cuenta', 'cuenta_banco__cuenta', 'contrato',
)
_RELACIONES_DETALLE = (
    'cuenta', 'concepto', 'contrato',
    'item__cuenta_venta', 'item__cuenta_compra',
    'item__cuenta_costo_venta', 'item__cuenta_inventario',
    'activo__cuenta_gasto', 'activo__cuenta_depreciacion', 'activo__centro_costo',
    'documento_detalle_afectado__documento__documento_tipo',
    'documento_detalle_afectado__documento__cuenta',
)


# ------------------------------------------------------------------ API ----

def contabilizar(documento_ids):
    """
    Contabiliza los documentos dados y devuelve cuántos quedaron contabilizados.

    El lote entero va en una transacción: si un documento falla, no queda ninguno
    contabilizado. El sistema anterior cortaba en el primer error dejando
    contabilizados los anteriores, que es un estado a medias imposible de deshacer
    desde la respuesta.
    """
    if not documento_ids:
        raise ValidationError({'ids': 'Este campo es requerido.'})
    with transaction.atomic():
        for documento_id in documento_ids:
            _contabilizar_documento(documento_id)
    return len(documento_ids)


def descontabilizar(documento_ids):
    """
    Borra los movimientos de los documentos dados y les quita el contabilizado.

    Mismo criterio de atomicidad que `contabilizar`.
    """
    if not documento_ids:
        raise ValidationError({'ids': 'Este campo es requerido.'})
    with transaction.atomic():
        for documento_id in documento_ids:
            _descontabilizar_documento(documento_id)
    return len(documento_ids)


# ------------------------------------------------------ un solo documento ----

def _contabilizar_documento(documento_id):
    documento = _documento_bloqueado(documento_id)

    if not documento.estado_aprobado:
        raise ValidationError(f'El documento {documento_id} debe estar aprobado.')
    if documento.estado_contabilizado:
        raise ValidationError(f'El documento {documento_id} ya está contabilizado.')

    periodo = _periodo(documento)

    campos_actualizar = ['estado_contabilizado']
    # Un documento anulado se marca contabilizado sin generar movimientos: no
    # tiene nada que llevar al mayor, pero si quedara sin contabilizar seguiría
    # saliendo como pendiente en `movimiento.analizar_inconsistencias` y el
    # periodo no se podría cerrar nunca.
    if not documento.estado_anulado:
        movimientos, campos_actualizar = _movimientos(documento, periodo, campos_actualizar)
        ConMovimiento.objects.bulk_create(movimientos)

    documento.estado_contabilizado = True
    documento.save(update_fields=campos_actualizar)


def _descontabilizar_documento(documento_id):
    documento = _documento_bloqueado(documento_id)

    if not documento.estado_contabilizado:
        raise ValidationError(f'El documento {documento_id} no está contabilizado.')

    # El periodo sale de los propios movimientos y no de recalcularlo desde la
    # fecha: un cierre se contabiliza en el periodo 13 y una prima en el de
    # `fecha_hasta`, así que recalcular buscaría un periodo distinto del que
    # realmente se afectó.
    periodo_ids = set(
        ConMovimiento.objects.filter(documento_id=documento_id)
        .values_list('periodo_id', flat=True)
    )
    for periodo_id in periodo_ids:
        periodo = ConPeriodo.objects.filter(pk=periodo_id).first()
        if periodo is not None and periodo.estado_bloqueado:
            raise ValidationError(
                f'El periodo {periodo_id} está bloqueado y no es posible '
                f'descontabilizar el documento {documento_id}.'
            )

    ConMovimiento.objects.filter(documento_id=documento_id).delete()
    documento.estado_contabilizado = False
    documento.save(update_fields=['estado_contabilizado'])


def _documento_bloqueado(documento_id):
    """Trae el documento bloqueando la fila, para que dos lotes no lo tomen a la vez."""
    documento = (
        # `of=('self',)` acota el bloqueo a la fila del documento: con el
        # select_related, PostgreSQL no permite un FOR UPDATE sobre los LEFT JOIN
        # que generan las FK nulables.
        GenDocumento.objects.select_for_update(of=('self',))
        .select_related(*_RELACIONES_DOCUMENTO)
        .filter(pk=documento_id)
        .first()
    )
    if documento is None:
        raise NotFound(f'El documento {documento_id} no existe.')
    return documento


# ---------------------------------------------------------------- periodo ----

def _periodo_id(documento):
    if documento.documento_tipo_id == DOCUMENTO_TIPO_CIERRE:
        # El cierre no cae en su mes: va al periodo 13, el de ajustes del año.
        fecha = _fecha_exigida(documento, 'fecha', documento.fecha)
        return ConPeriodo.calcular_id(fecha.year, MES_CIERRE)

    if documento.documento_tipo_id == DOCUMENTO_TIPO_PRIMA:
        fecha = _fecha_exigida(documento, 'fecha_hasta', documento.fecha_hasta)
    else:
        fecha = _fecha_exigida(documento, 'fecha_contable', documento.fecha_contable)
    return ConPeriodo.calcular_id(fecha.year, fecha.month)


def _fecha_exigida(documento, nombre, valor):
    # Las tres fechas son nullables y de ellas sale el periodo: sin fecha no hay
    # periodo que afectar, y conviene decirlo en vez de fallar al derivarlo.
    if valor is None:
        raise ValidationError(
            f'El documento {documento.pk} no tiene `{nombre}` y no se puede '
            f'determinar el periodo contable.'
        )
    return valor


def _periodo(documento):
    periodo_id = _periodo_id(documento)
    periodo = ConPeriodo.objects.filter(pk=periodo_id).first()
    if periodo is None:
        raise ValidationError(f'El periodo contable {periodo_id} no existe.')
    if periodo.estado_bloqueado:
        raise ValidationError(
            f'El periodo {periodo_id} está bloqueado y no es posible contabilizar '
            f'el documento {documento.pk}.'
        )
    return periodo


def _comprobante_id(documento):
    # El asiento lleva el comprobante que eligió el usuario; los demás tipos, el
    # de su tipo de documento.
    if documento.documento_tipo_id == DOCUMENTO_TIPO_ASIENTO:
        comprobante_id = documento.comprobante_id
    else:
        comprobante_id = documento.documento_tipo.comprobante_id
    if comprobante_id is None:
        raise ValidationError(
            f'El documento {documento.pk} no tiene comprobante: ni el documento ni '
            f'su tipo «{documento.documento_tipo.nombre}» lo tienen establecido.'
        )
    return comprobante_id


# ------------------------------------------------------------ movimientos ----

def _movimiento(comun, cuenta, signo, valor, detalle, etiqueta,
                contacto_id=None, centro_costo_id=None, base=CERO, cierre=False):
    """
    Arma un movimiento. `signo` positivo debita y negativo acredita.

    `etiqueta` solo se usa para decir qué cuenta falta cuando `cuenta` es None,
    que es el error más frecuente al contabilizar.
    """
    if cuenta is None:
        raise ValidationError(f'{etiqueta}: no tiene cuenta contable establecida.')
    if signo == 0:
        raise ValidationError(f'{etiqueta}: no se puede determinar débito o crédito.')

    debita = signo > 0
    return ConMovimiento(
        documento_id=comun['documento_id'],
        periodo_id=comun['periodo_id'],
        numero=comun['numero'],
        fecha=comun['fecha'],
        comprobante_id=comun['comprobante_id'],
        cuenta_id=cuenta.pk,
        naturaleza=DEBITO if debita else CREDITO,
        debito=valor if debita else CERO,
        credito=CERO if debita else valor,
        base=base or CERO,
        detalle=detalle,
        cierre=cierre,
        contacto_id=contacto_id,
        usuario_id=comun['usuario_id'],
        # El centro de costo solo se guarda si la cuenta lo exige; así el mayor no
        # se llena de centros de costo que nadie pidió y `analizar_inconsistencias`
        # sigue midiendo lo mismo.
        centro_costo_id=centro_costo_id if cuenta.exige_centro_costo else None,
    )


def _usuario_actual_id():
    usuario = obtener_usuario_actual()
    return usuario.pk if usuario is not None else None


def _movimientos(documento, periodo, campos_actualizar):
    """Devuelve (movimientos, campos del documento a guardar)."""
    tipo = documento.documento_tipo
    if (tipo.cobrar or tipo.pagar or tipo.venta or tipo.compra) and tipo.operacion not in (1, -1):
        # De `operacion` sale la naturaleza de casi todo el asiento; en 0 saldría
        # todo acreditado sin que nadie lo note.
        raise ValidationError(
            f'El tipo de documento «{tipo.nombre}» debe tener operación 1 o -1 '
            f'para poder contabilizarse.'
        )

    comun = {
        'documento_id': documento.pk,
        'periodo_id': periodo.pk,
        'numero': documento.numero,
        'fecha': documento.fecha_contable,
        'comprobante_id': _comprobante_id(documento),
        # Quién contabiliza. Fuera de un request (un comando, el shell) queda en
        # null, igual que en `gen_log`.
        'usuario_id': _usuario_actual_id(),
    }

    movimientos = []
    movimientos += _movimientos_cartera(documento, comun, campos_actualizar)
    movimientos += _movimientos_detalles(documento, comun)
    movimientos += _movimientos_impuestos(documento, comun)
    movimientos += _movimientos_banco(documento, comun)
    movimientos += _movimientos_provisiones(documento, comun)
    return movimientos, campos_actualizar


def _movimientos_cartera(documento, comun, campos_actualizar):
    """La contrapartida de cartera: el cliente que debe o el proveedor a quien se debe."""
    tipo = documento.documento_tipo
    movimientos = []
    centro_costo_id = documento.sede.centro_costo_id if documento.sede_id else None

    if tipo.cobrar:
        pagos = CERO
        for pago in (documento.documentos_pagos_documento
                     .filter(estado_anulado=False)
                     .select_related('cuenta_banco__cuenta')):
            movimientos.append(_movimiento(
                comun, pago.cuenta_banco.cuenta, tipo.operacion, pago.pago, 'PAGO',
                f'Pago {pago.pk}: la cuenta banco «{pago.cuenta_banco.nombre}»',
                contacto_id=documento.contacto_id, centro_costo_id=centro_costo_id,
            ))
            pagos += pago.pago

        pendiente = documento.total - pagos
        if pendiente > 0:
            movimientos.append(_movimiento(
                comun, tipo.cuenta_cobrar, tipo.operacion, pendiente, 'CLIENTE',
                f'La cuenta por cobrar del tipo de documento «{tipo.nombre}»',
                contacto_id=documento.contacto_id, centro_costo_id=centro_costo_id,
            ))
            # Se deja la cuenta en el documento para que el recibo posterior se
            # aplique contra la misma.
            documento.cuenta_id = tipo.cuenta_cobrar_id
            if 'cuenta' not in campos_actualizar:
                campos_actualizar.append('cuenta')

    if tipo.pagar:
        cuenta = tipo.cuenta_pagar
        if documento.forma_pago_id is not None:
            # En una compra la contrapartida la define cómo se pagó, no el tipo.
            cuenta = documento.forma_pago.cuenta
        valor = documento.total
        if documento.documento_tipo_id == DOCUMENTO_TIPO_SEGURIDAD_SOCIAL:
            # La cuenta del aporte se busca por `orden_compra`, que es donde la
            # seguridad social guarda su clase. Es texto libre, así que si no
            # coincide con ninguna configuración se cae a la cuenta por pagar.
            configuracion = (
                HumConfiguracionAporte.objects.select_related('cuenta')
                .filter(tipo=documento.orden_compra).first()
            )
            if configuracion is not None:
                cuenta = configuracion.cuenta
            valor = documento.subtotal

        movimientos.append(_movimiento(
            comun, cuenta, -tipo.operacion, valor, 'PROVEEDOR',
            f'La cuenta por pagar del tipo de documento «{tipo.nombre}»',
            contacto_id=documento.contacto_id,
        ))
        documento.cuenta_id = cuenta.pk
        if 'cuenta' not in campos_actualizar:
            campos_actualizar.append('cuenta')

    return movimientos


def _movimientos_detalles(documento, comun):
    movimientos = []
    detalles = (documento.documentos_detalles_documento_rel
                .select_related(*_RELACIONES_DETALLE))
    for detalle in detalles:
        if detalle.documento_detalle_afectado_id is not None:
            movimientos += _movimientos_afectado(documento, detalle, comun)
        elif detalle.tipo_registro == 'I':
            movimientos += _movimientos_item(documento, detalle, comun)
        elif detalle.tipo_registro == 'C':
            movimientos += _movimientos_cuenta(documento, detalle, comun)
        elif detalle.tipo_registro == 'N':
            movimientos += _movimientos_nomina(documento, detalle, comun)
        elif detalle.tipo_registro == 'S':
            movimientos += _movimientos_seguridad_social(documento, detalle, comun)
        elif detalle.tipo_registro == 'D':
            movimientos += _movimientos_depreciacion(documento, detalle, comun)
    return movimientos


def _movimientos_afectado(documento, detalle, comun):
    """
    Un recibo o un egreso descargan la cartera del documento que afectan, contra la
    cuenta con la que ese documento quedó contabilizado.
    """
    afectado = detalle.documento_detalle_afectado.documento
    tipo_afectado = afectado.documento_tipo
    movimientos = []

    if tipo_afectado.cobrar:
        movimientos.append(_movimiento(
            comun, afectado.cuenta, -tipo_afectado.operacion, detalle.precio, 'CLIENTE',
            f'Detalle {detalle.pk}: la cuenta por cobrar del documento referencia',
            contacto_id=detalle.contacto_id,
        ))

    if tipo_afectado.pagar:
        movimiento = _movimiento(
            comun, afectado.cuenta, tipo_afectado.operacion, detalle.precio, 'PROVEEDOR',
            f'Detalle {detalle.pk}: la cuenta por pagar del documento referencia',
            contacto_id=detalle.contacto_id,
        )
        movimientos.append(movimiento)
        # El detalle guarda con qué cuenta y naturaleza se cruzó, que es lo que
        # después lee el cruce de cartera.
        detalle.cuenta_id = movimiento.cuenta_id
        detalle.naturaleza = movimiento.naturaleza
        detalle.save(update_fields=['cuenta', 'naturaleza'])

    return movimientos


def _movimientos_item(documento, detalle, comun):
    tipo = documento.documento_tipo
    item = detalle.item
    movimientos = []
    if item is None:
        raise ValidationError(f'Detalle {detalle.pk}: no tiene item.')

    centro_costo_sede_id = documento.sede.centro_costo_id if documento.sede_id else None

    if tipo.venta:
        movimientos.append(_movimiento(
            comun, item.cuenta_venta, -tipo.operacion, detalle.subtotal, 'VENTA',
            f'El item «{item.nombre}»: la cuenta de venta',
            contacto_id=documento.contacto_id, centro_costo_id=centro_costo_sede_id,
        ))

        # El costo de venta solo lo mueven los tipos de venta que mueven
        # inventario; una nota débito no saca mercancía y no tiene costo que llevar.
        if tipo.operacion_inventario and detalle.costo > 0:
            costo_total = detalle.costo * detalle.cantidad
            movimientos.append(_movimiento(
                comun, item.cuenta_costo_venta, 1, costo_total, 'COSTO VENTA',
                f'El item «{item.nombre}»: la cuenta de costo de venta',
                contacto_id=documento.contacto_id, centro_costo_id=centro_costo_sede_id,
            ))
            movimientos.append(_movimiento(
                comun, item.cuenta_inventario, -1, costo_total, 'INVENTARIO',
                f'El item «{item.nombre}»: la cuenta de inventario',
                contacto_id=documento.contacto_id, centro_costo_id=centro_costo_sede_id,
            ))

    if tipo.compra:
        # Un item de inventario entra al almacén; uno que no lo es va directo al gasto.
        if item.inventario:
            cuenta, etiqueta, texto = item.cuenta_inventario, 'la cuenta de inventario', 'INVENTARIO COMPRA'
        else:
            cuenta, etiqueta, texto = item.cuenta_compra, 'la cuenta de compra', 'ITEM COMPRA'
        movimientos.append(_movimiento(
            comun, cuenta, tipo.operacion, detalle.subtotal, texto,
            f'El item «{item.nombre}»: {etiqueta}',
            contacto_id=documento.contacto_id, centro_costo_id=detalle.centro_costo_id,
        ))

    return movimientos


def _movimientos_cuenta(documento, detalle, comun):
    """
    Línea contable pura: la cuenta y la naturaleza las puso quien creó el detalle,
    no se derivan del tipo de documento.
    """
    cuenta = detalle.cuenta
    if cuenta is None:
        raise ValidationError(f'Detalle {detalle.pk}: no tiene cuenta.')
    if detalle.naturaleza not in (DEBITO, CREDITO):
        raise ValidationError(
            f'Detalle {detalle.pk}: la naturaleza debe ser «{DEBITO}» o «{CREDITO}».'
        )

    return [_movimiento(
        comun, cuenta, 1 if detalle.naturaleza == DEBITO else -1,
        detalle.precio, detalle.detalle, f'Detalle {detalle.pk}',
        contacto_id=detalle.contacto_id if cuenta.exige_contacto else None,
        centro_costo_id=detalle.centro_costo_id,
        base=detalle.base,
        cierre=documento.documento_tipo_id == DOCUMENTO_TIPO_CIERRE,
    )]


def _movimientos_nomina(documento, detalle, comun):
    if detalle.operacion == 0:
        return []

    contrato = _contrato_exigido(documento.contrato, f'Documento {documento.pk}')
    concepto_cuenta = (
        HumConceptoCuenta.objects.select_related('cuenta')
        .filter(concepto_id=detalle.concepto_id, tipo_costo_id=contrato.tipo_costo_id)
        .first()
    )
    cuenta = concepto_cuenta.cuenta if concepto_cuenta is not None else None

    texto = detalle.concepto.nombre if detalle.concepto_id else detalle.detalle
    if detalle.concepto_id and detalle.concepto.concepto_tipo_id in CONCEPTO_TIPOS_CON_EMPLEADO:
        contacto = documento.contacto
        texto = f'{contacto.numero_identificacion}-{contacto.nombre_corto}'

    return [_movimiento(
        comun, cuenta, detalle.operacion, detalle.pago, texto,
        f'Detalle {detalle.pk}: el concepto de nómina no tiene cuenta para el tipo de costo',
        contacto_id=detalle.contacto_id,
        centro_costo_id=contrato.centro_costo_id,
        base=detalle.base,
    )]


def _movimientos_seguridad_social(documento, detalle, comun):
    contrato = _contrato_exigido(detalle.contrato, f'Detalle {detalle.pk}')
    clase = detalle.detalle
    configuracion = (
        HumConfiguracionProvision.objects.select_related('cuenta_debito')
        .filter(tipo=clase, tipo_costo_id=contrato.tipo_costo_id).first()
    )
    cuenta = configuracion.cuenta_debito if configuracion is not None else None

    return [_movimiento(
        comun, cuenta, 1, detalle.precio, f'SS {clase} COSTO',
        f'Detalle {detalle.pk}: la seguridad social «{clase}»',
        contacto_id=documento.contacto_id,
        centro_costo_id=contrato.centro_costo_id,
    )]


def _movimientos_depreciacion(documento, detalle, comun):
    activo = detalle.activo
    if activo is None:
        raise ValidationError(f'Detalle {detalle.pk}: no tiene activo.')

    # El centro de costo sale del activo y no del documento: cada activo se
    # deprecia contra el suyo.
    centro_costo_id = activo.centro_costo_id
    return [
        _movimiento(
            comun, activo.cuenta_depreciacion, -1, detalle.precio,
            'Depreciacion acumulada', f'Detalle {detalle.pk}: la depreciación del activo',
            contacto_id=detalle.contacto_id, centro_costo_id=centro_costo_id,
            base=detalle.base,
        ),
        _movimiento(
            comun, activo.cuenta_gasto, 1, detalle.precio,
            'Gasto depreciacion', f'Detalle {detalle.pk}: el gasto del activo',
            contacto_id=detalle.contacto_id, centro_costo_id=centro_costo_id,
            base=detalle.base,
        ),
    ]


def _movimientos_impuestos(documento, comun):
    """
    Un movimiento por impuesto y por detalle, con la misma agrupación del sistema
    anterior.

    La naturaleza sale del signo del documento por el del impuesto: la retención
    tiene `operacion = -1` y por eso cae al lado contrario del IVA.
    """
    tipo = documento.documento_tipo
    agrupados = {}
    documentos_impuestos = (
        GenDocumentoImpuesto.objects
        .filter(documento_detalle__documento_id=documento.pk)
        .select_related('impuesto__cuenta')
    )
    for documento_impuesto in documentos_impuestos:
        clave = (documento_impuesto.documento_detalle_id, documento_impuesto.impuesto_id)
        acumulado = agrupados.setdefault(
            clave, {'impuesto': documento_impuesto.impuesto, 'total': CERO, 'base': CERO},
        )
        acumulado['total'] += documento_impuesto.total
        acumulado['base'] += documento_impuesto.base

    movimientos = []
    for (documento_detalle_id, _), acumulado in agrupados.items():
        impuesto = acumulado['impuesto']
        if impuesto.venta:
            signo = -(impuesto.operacion * tipo.operacion)
        elif impuesto.compra:
            signo = impuesto.operacion * tipo.operacion
        else:
            raise ValidationError(
                f'Detalle {documento_detalle_id}: el impuesto «{impuesto.nombre}» no '
                f'está marcado como de venta ni de compra.'
            )
        movimientos.append(_movimiento(
            comun, impuesto.cuenta, signo, acumulado['total'], 'IMPUESTO',
            f'Detalle {documento_detalle_id}: el impuesto «{impuesto.nombre}»',
            contacto_id=documento.contacto_id, base=acumulado['base'],
        ))
    return movimientos


def _movimientos_banco(documento, comun):
    """El pago entra al banco y el egreso sale de él."""
    if documento.documento_tipo_id == DOCUMENTO_TIPO_PAGO:
        signo = 1
    elif documento.documento_tipo_id == DOCUMENTO_TIPO_EGRESO:
        signo = -1
    else:
        return []

    if documento.cuenta_banco_id is None:
        raise ValidationError(f'El documento {documento.pk} no tiene cuenta banco.')
    return [_movimiento(
        comun, documento.cuenta_banco.cuenta, signo, documento.total, 'CUENTA BANCO',
        f'La cuenta banco «{documento.cuenta_banco.nombre}»',
    )]


def _movimientos_provisiones(documento, comun):
    """Las provisiones de nómina: cada una debita el costo y acredita el pasivo."""
    if documento.documento_tipo_id != DOCUMENTO_TIPO_NOMINA:
        return []

    movimientos = []
    contrato = None
    for campo, clase in PROVISIONES:
        valor = getattr(documento, campo)
        if valor <= 0:
            continue
        if contrato is None:
            contrato = _contrato_exigido(documento.contrato, f'Documento {documento.pk}')
        configuracion = (
            HumConfiguracionProvision.objects
            .select_related('cuenta_debito', 'cuenta_credito')
            .filter(tipo=clase, tipo_costo_id=contrato.tipo_costo_id).first()
        )
        debito = configuracion.cuenta_debito if configuracion is not None else None
        credito = configuracion.cuenta_credito if configuracion is not None else None
        etiqueta = f'La provisión de {clase.lower()}'
        movimientos.append(_movimiento(
            comun, debito, 1, valor, f'PROVISION {clase} DEB', etiqueta,
            contacto_id=documento.contacto_id, centro_costo_id=contrato.centro_costo_id,
        ))
        movimientos.append(_movimiento(
            comun, credito, -1, valor, f'PROVISION {clase} CRE', etiqueta,
            contacto_id=documento.contacto_id, centro_costo_id=contrato.centro_costo_id,
        ))
    return movimientos


def _contrato_exigido(contrato, etiqueta):
    # De `contrato.tipo_costo` sale la cuenta de todo lo de nómina, así que sin
    # contrato no hay asiento posible.
    if contrato is None:
        raise ValidationError(f'{etiqueta}: no tiene contrato y es un documento de nómina.')
    return contrato
