"""
Validación de los saldos de los créditos de los empleados.

Lo abonado a un crédito lo escribe `programacion._afectar_creditos` al aprobar o
desaprobar una nómina, sumando y restando sobre lo guardado. Si algo se salta
ese camino —un documento de nómina anulado, una edición a mano, un dato
migrado— el saldo queda desfasado y la nómina descuenta de más o deja de
descontar. `validar` lo recalcula desde las líneas que lo originan.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum

from general.models import GenDocumentoDetalle
from humano.models import HumCredito

CAMPOS_CREDITO = ('abono', 'saldo', 'cuota_actual')


def _esperados():
    """
    `{credito_id: (abono, cuotas)}` desde las líneas de nómina que descontaron
    cada crédito, en documentos aprobados y sin anular.

    El `order_by()` vacío no sobra: el modelo ordena por `-id`, y ese orden se
    metería en el GROUP BY y devolvería una fila por línea en vez de una por
    crédito.
    """
    return {
        credito_id: (abono, cuotas)
        for credito_id, abono, cuotas in (
            GenDocumentoDetalle.objects
            .filter(
                credito__isnull=False,
                documento__estado_aprobado=True,
                documento__estado_anulado=False,
            )
            .order_by()
            .values('credito_id')
            .annotate(abono=Sum('pago'), cuotas=Count('id'))
            .values_list('credito_id', 'abono', 'cuotas')
        )
    }


def validar():
    """
    Recalcula `abono`, `saldo` y `cuota_actual` de todos los créditos y corrige
    los que difieren; los que cuadran no se tocan. Devuelve cuántos corrigió.

    Los créditos se bloquean antes de calcular: así una nómina que se apruebe en
    el medio espera a que esto termine, en vez de abonar sobre un saldo que acá
    se va a sobrescribir con un cálculo que no la vio.
    """
    with transaction.atomic():
        creditos = list(HumCredito.objects.select_for_update())
        esperados = _esperados()

        corregidos = []
        for credito in creditos:
            abono, cuotas = esperados.get(credito.id, (Decimal('0'), 0))
            saldo = credito.total - abono
            if (credito.abono, credito.saldo, credito.cuota_actual) != (abono, saldo, cuotas):
                credito.abono = abono
                credito.saldo = saldo
                credito.cuota_actual = cuotas
                corregidos.append(credito)
        HumCredito.objects.bulk_update(corregidos, CAMPOS_CREDITO)
    return len(corregidos)
