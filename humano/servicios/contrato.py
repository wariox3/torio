from django.db.models import Count, Q
from django.utils import timezone

from humano.models import HumContrato


def resumen(hoy=None):
    """
    Cantidades del tablero de inicio de humano, en un solo `aggregate`.

    Activo es lo que no está terminado (`estado_terminado`), no lo que tiene
    `fecha_hasta` futura: en un indefinido esa fecha no marca el fin del contrato.
    Activos y terminados suman el total.

    Del mes de `hoy`: ingreso es un contrato que empieza en el mes (terminado o
    no), y retiro uno terminado cuya `fecha_hasta` cae en el mes, que es donde
    `terminar_contrato` guarda la fecha de terminación.
    """
    hoy = hoy or timezone.localdate()
    ingresa_en_el_mes = Q(fecha_desde__year=hoy.year, fecha_desde__month=hoy.month)
    termina_en_el_mes = Q(fecha_hasta__year=hoy.year, fecha_hasta__month=hoy.month)

    agregados = HumContrato.objects.aggregate(
        contratos=Count('id'),
        contratos_activos=Count('id', filter=Q(estado_terminado=False)),
        contratos_terminados=Count('id', filter=Q(estado_terminado=True)),
        ingresos_mes=Count('id', filter=ingresa_en_el_mes),
        retiros_mes=Count('id', filter=termina_en_el_mes & Q(estado_terminado=True)),
    )
    return {'fecha': hoy, **agregados}
