from datetime import date

from general.models import GenFestivo
from turno.models import TurTurno


def calcular_mes(secuencia, anio, mes, posicion_inicial, dia_desde, dia_hasta):
    """
    Aplica la secuencia como patrón cíclico sobre un mes (no persiste).

    El patrón son los primeros `secuencia.dias` slots (`dia_1`..`dia_{dias}`),
    cada uno con el `codigo` de un `TurTurno` (vacío = descanso). El patrón se
    repite cada `secuencia.dias` días a lo largo del mes; `posicion_inicial`
    (1-based) indica qué slot del patrón corresponde al día 1 del mes.

    Solo se devuelven los días entre `dia_desde` y `dia_hasta` (inclusive), pero el
    ciclo sigue anclado en el día 1: cada día conserva el turno que le toca del
    patrón, aunque el rango empiece más tarde.

    Retorna una lista de dicts, uno por día dentro del rango:
        {dia, fecha, turno_codigo, turno_id, turno_nombre,
         horas, horas_diurnas, horas_nocturnas, festivo}
    """
    n = secuencia.dias

    # Patrón cíclico: codigo de turno por cada posición (vacío = descanso).
    patron = [getattr(secuencia, f'dia_{i}') or None for i in range(1, n + 1)]

    festivos = set(
        GenFestivo.objects
        .filter(fecha__year=anio, fecha__month=mes)
        .values_list('fecha', flat=True)
    )

    codigos = {c for c in patron if c}
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}

    dias = []
    for dia in range(dia_desde, dia_hasta + 1):
        indice = ((posicion_inicial - 1) + (dia - 1)) % n
        codigo = patron[indice]
        turno = turnos.get(codigo) if codigo else None
        fecha = date(anio, mes, dia)
        dias.append({
            'dia': dia,
            'fecha': fecha.isoformat(),
            'turno_codigo': codigo,
            'turno_id': turno.id if turno else None,
            'turno_nombre': turno.nombre if turno else None,
            'horas': turno.horas if turno else 0,
            'horas_diurnas': turno.horas_diurnas if turno else 0,
            'horas_nocturnas': turno.horas_nocturnas if turno else 0,
            'festivo': fecha in festivos,
        })

    return dias
