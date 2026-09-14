"""
Pagos que recibe un documento al emitirse, cada uno contra una cuenta bancaria.

`GenDocumento.pago` es la suma de los pagos no anulados y **solo se escribe acá**:
el cliente no lo manda. Es lo que `aprobar` resta del total para dejar el saldo en
cartera, y contabilizar lleva cada pago a la cuenta contable de su cuenta bancaria.
Si esas dos cosas no salieran de las mismas filas, cartera y contabilidad
mostrarían saldos distintos para el mismo documento.

El ciclo sigue al del documento:

- Mientras es modificable, los pagos se registran, se editan y se eliminan.
- Aprobado, ya no se tocan: un pago que no fue se **anula**. La fila conserva su
  valor y queda con `estado_anulado`, para que se vea qué pasó.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import NotFound, ValidationError

from general.models import GenDocumento, GenDocumentoPago
from general.servicios.documento import (
    DOCUMENTO_CLASES_CON_CARTERA,
    DOCUMENTO_TIPOS_NOTA_CREDITO,
)


def _documento_bloqueado(documento_id):
    try:
        return GenDocumento.objects.select_for_update().get(pk=documento_id)
    except GenDocumento.DoesNotExist:
        raise NotFound('Documento no encontrado.')


def _pago_con_documento_bloqueado(pago_id):
    """
    Bloquea el documento y después el pago. Es el mismo orden en que bloquean
    `aprobar` y `registrar`: al revés, dos peticiones sobre el mismo documento se
    podrían quedar esperando la una a la otra.
    """
    documento_id = (
        GenDocumentoPago.objects.filter(pk=pago_id)
        .values_list('documento_id', flat=True)
        .first()
    )
    if documento_id is None:
        raise NotFound('Pago no encontrado.')
    documento = _documento_bloqueado(documento_id)
    pago = GenDocumentoPago.objects.select_for_update().get(pk=pago_id)
    return documento, pago


def _validar_modificable(documento):
    if not documento.es_mutable():
        raise ValidationError('El documento no es modificable.')


def _validar_cuenta_banco(cuenta_banco):
    """Contabilizar lleva el pago a la cuenta contable de su cuenta bancaria."""
    if cuenta_banco.cuenta_id is None:
        raise ValidationError({
            'cuenta_banco': (
                f'La cuenta bancaria «{cuenta_banco.nombre}» no tiene cuenta contable.'
            ),
        })


def _actualizar_pago(documento):
    """Deja `documento.pago` en la suma de sus pagos no anulados. Devuelve los campos tocados."""
    documento.pago = (
        documento.documentos_pagos_documento
        .filter(estado_anulado=False)
        .aggregate(total=Sum('pago'))['total']
        or Decimal('0')
    )
    return ['pago']


def registrar(documento_id, cuenta_banco, pago):
    """
    Registra un pago sobre un documento modificable.

    No se compara contra el total: mientras el documento es modificable el total
    se mueve con cada detalle. Eso lo valida `aprobar`.
    """
    with transaction.atomic():
        documento = _documento_bloqueado(documento_id)
        _validar_modificable(documento)
        # Contabilizar solo lleva pagos al banco en los tipos que cobran: en otro
        # tipo el pago bajaría el saldo en cartera sin un movimiento que lo respalde.
        if not documento.documento_tipo.cobrar:
            raise ValidationError('El tipo de documento no recibe pagos.')
        _validar_cuenta_banco(cuenta_banco)

        nuevo = GenDocumentoPago.objects.create(
            documento=documento, cuenta_banco=cuenta_banco, pago=pago,
        )
        documento.save(update_fields=_actualizar_pago(documento))
    return nuevo


def actualizar(pago_id, datos):
    """Cambia la cuenta bancaria o el valor de un pago de un documento modificable."""
    with transaction.atomic():
        documento, pago = _pago_con_documento_bloqueado(pago_id)
        _validar_modificable(documento)
        if 'cuenta_banco' in datos:
            _validar_cuenta_banco(datos['cuenta_banco'])
            pago.cuenta_banco = datos['cuenta_banco']
        if 'pago' in datos:
            pago.pago = datos['pago']
        pago.save(update_fields=['cuenta_banco', 'pago'])
        documento.save(update_fields=_actualizar_pago(documento))
    return pago


def eliminar(pago_id):
    """Borra un pago de un documento modificable."""
    with transaction.atomic():
        documento, pago = _pago_con_documento_bloqueado(pago_id)
        _validar_modificable(documento)
        pago.delete()
        documento.save(update_fields=_actualizar_pago(documento))


def anular(pago_id):
    """
    Anula un pago de un documento aprobado: deja de contar en `documento.pago` y
    lo que se había pagado vuelve a quedar pendiente en cartera.

    Con el documento contabilizado no se puede: el pago ya está en el mayor y hay
    que descontabilizar primero.
    """
    with transaction.atomic():
        documento, pago = _pago_con_documento_bloqueado(pago_id)
        if pago.estado_anulado:
            raise ValidationError('El pago ya está anulado.')
        if not documento.estado_aprobado:
            raise ValidationError(
                'El documento no está aprobado: el pago se elimina, no se anula.'
            )
        if documento.estado_anulado:
            raise ValidationError('El documento está anulado.')
        if documento.estado_contabilizado:
            raise ValidationError('El documento está contabilizado.')
        # La nota crédito descargó `total - pago` de su factura al aprobarse, y
        # desaprobarla devuelve `total - pago` con el pago que tenga en ese momento.
        # Cambiar el pago en el medio dejaría la factura con un saldo que no cuadra.
        if (documento.documento_tipo_id in DOCUMENTO_TIPOS_NOTA_CREDITO
                and documento.documento_referencia_id is not None):
            raise ValidationError(
                'El pago de una nota crédito no se anula: desapruebe la nota.'
            )

        pago.estado_anulado = True
        pago.save(update_fields=['estado_anulado'])

        campos_actualizar = _actualizar_pago(documento)
        # La misma fórmula de `_afectar_documento_referencia` y
        # `_aplicar_afectacion_documento`, los otros puntos que mueven el saldo de
        # un documento ya aprobado.
        if documento.documento_tipo.documento_clase_id in DOCUMENTO_CLASES_CON_CARTERA:
            documento.pendiente = documento.total - (documento.afectado + documento.pago)
            campos_actualizar.append('pendiente')
        documento.save(update_fields=campos_actualizar)
    return pago
