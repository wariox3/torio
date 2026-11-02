"""
Detectores de pendientes de contabilidad para el comando `analizar_pendientes`.

Corren dentro del schema del tenant. Cada uno devuelve `(cantidad, mensaje)` o
`None` si no hay nada pendiente.
"""
from contabilidad.models import ConPeriodo


def periodo_anterior_abierto(hoy):
    """
    Periodos sin cerrar de meses anteriores al actual. El id es `anio*100+mes`, así
    que el periodo 13 (cierre) del año en curso queda fuera solo: se cierra al año
    siguiente. Los periodos solo existen si el tenant los creó, así que a quien no
    lleva contabilidad no le sale este aviso.
    """
    actual = ConPeriodo.calcular_id(hoy.year, hoy.month)
    cantidad = ConPeriodo.objects.filter(estado_cerrado=False, id__lt=actual).count()
    if not cantidad:
        return None
    if cantidad == 1:
        return cantidad, 'Hay 1 periodo anterior abierto'
    return cantidad, f'Hay {cantidad} periodos anteriores abiertos'
