from django.db.models import Count, Q

from humano.models import HumContrato


def resumen():
    """
    Cantidades del tablero de inicio de humano, en un solo `aggregate`.

    Activo es lo que no está terminado (`estado_terminado`), no lo que tiene
    `fecha_hasta` futura: en un indefinido esa fecha no marca el fin del contrato.
    Activos y terminados suman el total.
    """
    return HumContrato.objects.aggregate(
        contratos=Count('id'),
        contratos_activos=Count('id', filter=Q(estado_terminado=False)),
        contratos_terminados=Count('id', filter=Q(estado_terminado=True)),
    )
