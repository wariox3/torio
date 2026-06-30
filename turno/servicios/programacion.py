from django.db import transaction

from general.models import GenFestivo
from turno.models import TurProgramacion, TurTurno


class ProgramacionExistenteError(ValueError):
    """
    Se intentó crear programación en fechas que el contrato ya tiene ocupadas.

    Lleva en `programaciones` las filas `TurProgramacion` en conflicto
    (con `turno` precargado) para que la vista las devuelva al front.
    """

    def __init__(self, programaciones):
        self.programaciones = programaciones
        fechas = [p.fecha.isoformat() for p in programaciones]
        super().__init__(f'Ya existe programación para: {fechas}.')


def crear_programacion(contrato, documento_detalle, items):
    """
    Crea filas de `TurProgramacion` para un contrato a partir de una lista de
    items `{fecha, turno_codigo}` (fecha: `date`; turno_codigo vacío = descanso).

    - El turno se resuelve por `codigo` contra `TurTurno`.
    - `festivo` se marca consultando `GenFestivo`.
    - Las horas se denormalizan desde el turno resuelto.
    - No hay upsert: si ya existe programación para `(contrato, fecha)` —o si el
      array trae fechas repetidas, o un `turno_codigo` inexistente— se aborta
      con `ValueError` sin guardar nada.

    Retorna la cantidad de filas creadas.
    """
    fechas = [item['fecha'] for item in items]

    repetidas = sorted({f.isoformat() for f in fechas if fechas.count(f) > 1})
    if repetidas:
        raise ValueError(f'Fechas repetidas en la solicitud: {repetidas}.')

    existentes = list(
        TurProgramacion.objects
        .select_related('turno')
        .filter(contrato=contrato, fecha__in=fechas)
        .order_by('fecha')
    )
    if existentes:
        raise ProgramacionExistenteError(existentes)

    codigos = {(item.get('turno_codigo') or '').strip() for item in items}
    codigos.discard('')
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}
    faltantes = sorted(codigos - turnos.keys())
    if faltantes:
        raise ValueError(f'Turnos inexistentes: {faltantes}.')

    festivos = set(
        GenFestivo.objects.filter(fecha__in=fechas).values_list('fecha', flat=True)
    )

    nuevos = []
    for item in items:
        codigo = (item.get('turno_codigo') or '').strip() or None
        turno = turnos.get(codigo) if codigo else None
        nuevos.append(TurProgramacion(
            contrato=contrato,
            fecha=item['fecha'],
            documento_detalle=documento_detalle,
            turno=turno,
            festivo=item['fecha'] in festivos,
            horas=turno.horas if turno else 0,
            horas_diurnas=turno.horas_diurnas if turno else 0,
            horas_nocturnas=turno.horas_nocturnas if turno else 0,
        ))

    with transaction.atomic():
        TurProgramacion.objects.bulk_create(nuevos)

    return len(nuevos)
