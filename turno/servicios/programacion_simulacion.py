import calendar
from datetime import date

from django.db import transaction

from general.models import GenFestivo
from turno.models import TurProgramacionSimulacion, TurPrototipo, TurTurno


def simular(documento_detalle_id, anio, mes):
    """
    Explota los prototipos de un `documento_detalle` en filas de
    `TurProgramacionSimulacion` para un mes dado (una fila por día y prototipo).

    Cada prototipo resuelve su `secuencia` como patrón cíclico anclado en
    `fecha_inicio`/`posicion`: el patrón son los primeros `secuencia.dias` slots
    (`dia_1`..`dia_{dias}`), cada uno con el `codigo` de un `TurTurno` (vacío =
    descanso). En `fecha_inicio` el patrón está en `posicion` (1-based) y se
    repite cada `secuencia.dias` días; para cada día del mes se calcula qué slot
    aplica según los días transcurridos desde `fecha_inicio`.

    - El turno se resuelve por `codigo` contra `TurTurno`; código vacío = descanso.
    - `festivo` se marca consultando `GenFestivo`.
    - Las horas se denormalizan desde el turno resuelto.
    - Vacía toda la tabla buffer antes de cargar (una sola corrida a la vez).

    Retorna la cantidad de filas creadas.
    """
    prototipos = list(
        TurPrototipo.objects
        .select_related('secuencia', 'contrato')
        .filter(documento_detalle_id=documento_detalle_id)
    )

    dias_mes = calendar.monthrange(anio, mes)[1]

    festivos = set(
        GenFestivo.objects
        .filter(fecha__year=anio, fecha__month=mes)
        .values_list('fecha', flat=True)
    )

    # Códigos de turno referenciados por los patrones (dia_1..dia_{dias}) de todas
    # las secuencias, para resolver los turnos en una sola consulta.
    codigos = set()
    for prototipo in prototipos:
        secuencia = prototipo.secuencia
        if secuencia and secuencia.dias:
            for i in range(1, secuencia.dias + 1):
                codigo = getattr(secuencia, f'dia_{i}')
                if codigo:
                    codigos.add(codigo)
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}

    nuevos = []
    for prototipo in prototipos:
        secuencia = prototipo.secuencia
        if secuencia is None or not secuencia.dias:
            continue
        n = secuencia.dias
        patron = [getattr(secuencia, f'dia_{i}') or None for i in range(1, n + 1)]
        for dia in range(1, dias_mes + 1):
            fecha = date(anio, mes, dia)
            offset = (fecha - prototipo.fecha_inicio).days
            indice = ((prototipo.posicion - 1) + offset) % n
            codigo = patron[indice]
            turno = turnos.get(codigo) if codigo else None
            nuevos.append(TurProgramacionSimulacion(
                fecha=fecha,
                contrato=prototipo.contrato,
                documento_detalle_id=documento_detalle_id,
                posicion=prototipo.posicion,
                turno=turno,
                festivo=fecha in festivos,
                horas=turno.horas if turno else 0,
                horas_diurnas=turno.horas_diurnas if turno else 0,
                horas_nocturnas=turno.horas_nocturnas if turno else 0,
            ))

    with transaction.atomic():
        TurProgramacionSimulacion.objects.all().delete()
        TurProgramacionSimulacion.objects.bulk_create(nuevos)

    return len(nuevos)
