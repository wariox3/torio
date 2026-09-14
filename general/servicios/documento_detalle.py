from decimal import Decimal

from rest_framework.exceptions import ValidationError

from general.models import GenDocumentoDetalle
from general.servicios.documento import (
    DOCUMENTO_TIPO_TRASLADO_ALMACEN,
    DOCUMENTO_TIPOS_REMISION,
    sincronizar_impuestos,
)


def asignar_operacion(detalle):
    """
    Fija en qué sentido mueve saldos una línea de item. Sale del tipo del
    documento, no de lo que mande el cliente.

    - `operacion_inventario` es la de `GenDocumentoTipo`, y solo si el item lleva
      inventario: un servicio no tiene existencias que mover. El traslado es la
      excepción: cada línea saca de un almacén o mete en otro, así que el sentido
      lo trae la línea y acá solo se valida.
    - En remisión y su devolución el movimiento va sobre `disponible` con la
      `operacion_remision` del tipo, lleve o no inventario el item.
    - `cantidad_operada` es la cantidad con ese signo, que es lo que `aprobar`
      suma al saldo.

    Una línea que no es de item (`tipo_registro` distinto de 'I') no opera nada.

    Corre al crear y al editar: si solo corriera al crear, cambiar la cantidad
    dejaría `cantidad_operada` con la anterior y aprobar movería otra.
    """
    operacion_solicitada = detalle.operacion_inventario
    detalle.operacion_inventario = 0
    detalle.operacion_remision = 0
    detalle.cantidad_operada = Decimal('0')
    if detalle.tipo_registro != 'I':
        return

    documento_tipo = detalle.documento.documento_tipo
    cantidad = detalle.cantidad or Decimal('0')
    detalle.cantidad_pendiente = cantidad

    if detalle.item_id is not None and detalle.item.inventario:
        if documento_tipo.pk == DOCUMENTO_TIPO_TRASLADO_ALMACEN:
            if operacion_solicitada not in (1, -1):
                raise ValidationError({
                    'operacion_inventario': (
                        'En un traslado de almacén debe ser 1 (entra) o -1 (sale).'
                    ),
                })
            detalle.operacion_inventario = operacion_solicitada
        else:
            detalle.operacion_inventario = documento_tipo.operacion_inventario
        detalle.cantidad_operada = cantidad * detalle.operacion_inventario

    if documento_tipo.pk in DOCUMENTO_TIPOS_REMISION:
        detalle.operacion_remision = documento_tipo.operacion_remision
        detalle.cantidad_operada = cantidad * documento_tipo.operacion_remision


def crear_detalle(documento, datos):
    """Crea un detalle ya validado sobre un documento existente (sin recalcular el documento)."""
    datos = dict(datos)
    impuestos = datos.pop('impuestos_ids', [])
    datos.pop('documento', None)  # el documento lo fija el padre
    detalle = GenDocumentoDetalle(documento=documento, **datos)
    asignar_operacion(detalle)
    detalle.save()
    sincronizar_impuestos(detalle, impuestos)
    detalle.calcular()
    detalle.save()
    return detalle
