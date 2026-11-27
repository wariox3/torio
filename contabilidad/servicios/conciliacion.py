"""
Conciliación bancaria: lo que la conciliación exige a quien borra movimientos.
"""
from rest_framework.exceptions import ValidationError

from contabilidad.models import ConConciliacionDetalle


def liberar_movimientos(movimiento_ids):
    """
    Prepara el borrado de un asiento quitándolo de las conciliaciones.

    Los movimientos se borran siempre por asiento completo (descontabilizar un
    documento, eliminar un saldo inicial), así que esto se llama con todos los
    movimientos del asiento y dentro de la misma transacción del borrado:

    - Si alguno está conciliado, no se borra ninguno: el banco ya confirmó ese
      valor, y cambiarlo dejaría de cuadrar una conciliación sin que nadie lo
      note. Hay que desconciliarlo primero.
    - Los detalles pendientes (cargados en una conciliación pero sin cruzar) se
      borran: no tienen nada del extracto, y al volver a contabilizar el
      movimiento nuevo se carga otra vez como pendiente.
    """
    detalles = ConConciliacionDetalle.objects.filter(movimiento_id__in=movimiento_ids)

    conciliados = list(
        detalles.filter(estado_conciliado=True)
        .select_related('conciliacion__cuenta_banco')
    )
    if conciliados:
        conciliaciones = {
            d.conciliacion.id: d.conciliacion for d in conciliados if d.conciliacion is not None
        }
        descripciones = [
            f'{c.id} ({c.cuenta_banco.nombre if c.cuenta_banco else "sin cuenta"}, '
            f'{c.fecha_desde} a {c.fecha_hasta})'
            for c in sorted(conciliaciones.values(), key=lambda c: c.id)
        ]
        if not descripciones:
            detail = 'Tiene movimientos conciliados. Desconcílielos primero.'
        elif len(descripciones) == 1:
            detail = f'Tiene movimientos conciliados en la conciliación {descripciones[0]}. Desconcílielos primero.'
        else:
            detail = (
                f'Tiene movimientos conciliados en las conciliaciones '
                f'{", ".join(descripciones)}. Desconcílielos primero.'
            )
        raise ValidationError({'detail': detail, 'errores': sorted(conciliaciones)})

    detalles.delete()
