"""
Conciliación bancaria: cargar los movimientos de libros a una conciliación,
cruzarlos contra el extracto, y lo que la conciliación exige a quien borra
movimientos.
"""
from collections import defaultdict

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError

from contabilidad.models import (
    ConConciliacion,
    ConConciliacionDetalle,
    ConConciliacionSoporte,
    ConMovimiento,
)


def cargar(conciliacion_id):
    """
    Carga como detalles los movimientos de libros que la conciliación debe cruzar.

    Son los movimientos de la cuenta contable de la cuenta bancaria:

    - del rango de la conciliación, y
    - anteriores al rango que estuvieron en una conciliación previa de la misma
      cuenta bancaria y nunca se conciliaron (el cheque girado en septiembre que
      el banco cobró en octubre): así se arrastran las partidas conciliatorias.

    Nunca carga uno ya conciliado en cualquier conciliación, uno que ya está en
    esta —volver a cargar después de contabilizar más documentos solo agrega lo
    que falta— ni los de saldo inicial o cierre, que no son transacciones del
    banco y nunca van a salir en el extracto.

    Devuelve cuántos detalles creó.
    """
    with transaction.atomic():
        conciliacion = (
            # `of=('self',)`: PostgreSQL no permite FOR UPDATE sobre el LEFT JOIN
            # de una FK nulable. Bloquea la conciliación para que dos cargas
            # simultáneas no dupliquen detalles.
            ConConciliacion.objects.select_for_update(of=('self',))
            .select_related('cuenta_banco')
            .filter(pk=conciliacion_id)
            .first()
        )
        if conciliacion is None:
            raise NotFound('Conciliación no encontrada.')
        cuenta_banco = conciliacion.cuenta_banco
        if cuenta_banco is None:
            raise ValidationError({'detail': 'La conciliación no tiene cuenta bancaria.'})
        if cuenta_banco.cuenta_id is None:
            raise ValidationError({
                'detail': f'La cuenta bancaria {cuenta_banco.nombre} no tiene cuenta contable asignada.',
            })

        # Los `movimiento__isnull=False` no sobran: un NULL dentro de un NOT IN
        # hace que no salga ninguna fila.
        con_movimiento = ConConciliacionDetalle.objects.filter(movimiento__isnull=False)
        conciliados = con_movimiento.filter(estado_conciliado=True).values('movimiento_id')
        en_esta = con_movimiento.filter(conciliacion=conciliacion).values('movimiento_id')
        en_anteriores = con_movimiento.filter(
            conciliacion__cuenta_banco=cuenta_banco,
            conciliacion__fecha_desde__lt=conciliacion.fecha_desde,
        ).values('movimiento_id')

        movimientos = (
            ConMovimiento.objects
            .filter(cuenta_id=cuenta_banco.cuenta_id, saldo_inicial=False, cierre=False)
            .filter(
                Q(fecha__gte=conciliacion.fecha_desde, fecha__lte=conciliacion.fecha_hasta)
                | Q(fecha__lt=conciliacion.fecha_desde, id__in=en_anteriores)
            )
            .exclude(id__in=conciliados)
            .exclude(id__in=en_esta)
            .order_by('fecha', 'id')
        )

        detalles = ConConciliacionDetalle.objects.bulk_create(
            [
                ConConciliacionDetalle(
                    conciliacion=conciliacion,
                    movimiento_id=movimiento.id,
                    fecha=movimiento.fecha,
                    debito=movimiento.debito,
                    credito=movimiento.credito,
                    detalle=movimiento.detalle,
                    cuenta_id=movimiento.cuenta_id,
                    contacto_id=movimiento.contacto_id,
                    documento_id=movimiento.documento_id,
                )
                for movimiento in movimientos.iterator(chunk_size=2000)
            ],
            batch_size=500,
        )
    return len(detalles)


def conciliar(conciliacion_id, dias=0):
    """
    Cruza automáticamente los detalles pendientes contra el extracto pendiente.

    Las parejas son 1 a 1: un detalle con una línea del extracto del mismo lado
    (débito con débito, crédito con crédito: el extracto se importa ya con la
    naturaleza de los libros) y por el mismo valor exacto, con fechas que no se
    separen más de `dias`. Entre varios candidatos gana el de fecha más cercana,
    y a igual distancia el de menor fecha e id; cada línea se usa una sola vez.
    Ambos lados quedan con `estado_conciliado`.

    No guarda qué cruzó con qué: solo el estado de cada lado. Se puede volver a
    ejecutar —solo toma lo que sigue pendiente—, por ejemplo con más `dias`.

    Devuelve cuántos pares cruzó.
    """
    with transaction.atomic():
        # Bloquea la conciliación: una carga, una importación o un limpiar en curso
        # sobre ella terminan antes, y dos conciliar no usan la misma línea.
        if not ConConciliacion.objects.select_for_update().filter(pk=conciliacion_id).exists():
            raise NotFound('Conciliación no encontrada.')

        soportes_por_llave = defaultdict(list)
        soportes = (
            ConConciliacionSoporte.objects
            .filter(conciliacion_id=conciliacion_id, estado_conciliado=False)
            .order_by('fecha', 'id')
        )
        for soporte in soportes:
            llave = _llave(soporte)
            if llave is not None:
                soportes_por_llave[llave].append(soporte)

        detalles = (
            ConConciliacionDetalle.objects
            .filter(conciliacion_id=conciliacion_id, estado_conciliado=False)
            .order_by('fecha', 'id')
        )
        detalles_cruzados = []
        soportes_cruzados = []
        for detalle in detalles:
            candidatos = soportes_por_llave.get(_llave(detalle))
            if not candidatos:
                continue
            # `candidatos` está ordenado por fecha e id, así que `min` desempata
            # por el primero: el de menor fecha e id.
            mejor = min(
                (s for s in candidatos if abs((s.fecha - detalle.fecha).days) <= dias),
                key=lambda s: abs((s.fecha - detalle.fecha).days),
                default=None,
            )
            if mejor is None:
                continue
            candidatos.remove(mejor)
            detalle.estado_conciliado = True
            mejor.estado_conciliado = True
            detalles_cruzados.append(detalle)
            soportes_cruzados.append(mejor)

        ConConciliacionDetalle.objects.bulk_update(detalles_cruzados, ['estado_conciliado'], batch_size=500)
        ConConciliacionSoporte.objects.bulk_update(soportes_cruzados, ['estado_conciliado'], batch_size=500)
    return len(detalles_cruzados)


def desconciliar(conciliacion_id):
    """
    Devuelve a pendiente todo lo conciliado de la conciliación, en ambos lados.

    Es todo o nada porque no se guarda qué cruzó con qué: sin el par no hay forma
    de soltar una pareja sola.

    Devuelve cuántos detalles y cuántas líneas del extracto desmarcó.
    """
    with transaction.atomic():
        if not ConConciliacion.objects.select_for_update().filter(pk=conciliacion_id).exists():
            raise NotFound('Conciliación no encontrada.')
        detalles = ConConciliacionDetalle.objects.filter(
            conciliacion_id=conciliacion_id, estado_conciliado=True,
        ).update(estado_conciliado=False)
        soportes = ConConciliacionSoporte.objects.filter(
            conciliacion_id=conciliacion_id, estado_conciliado=True,
        ).update(estado_conciliado=False)
    return detalles, soportes


def _llave(linea):
    """(lado, valor) de un detalle o una línea del extracto; None si no tiene valor."""
    if linea.debito > 0:
        return ('D', linea.debito)
    if linea.credito > 0:
        return ('C', linea.credito)
    return None


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
