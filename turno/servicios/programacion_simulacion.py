import calendar
from datetime import date

from django.db import transaction

from general.models import GenFestivo
from turno.models import TurProgramacionSimulacion, TurTurno

# Ranuras por día de semana, indexadas por date.weekday() (lunes=0 … domingo=6)
_SLOTS_SEMANA = ('lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo')
# Todas las ranuras de la secuencia que guardan un código de turno
_CAMPOS_DIAS = tuple(f'dia_{n}' for n in range(1, 32))
_CAMPOS_CODIGO = (*_CAMPOS_DIAS, *_SLOTS_SEMANA, 'festivo', 'domingo_festivo')


def _codigo_para_fecha(secuencia, fecha, es_festivo):
    """
    Resuelve el código de turno de la secuencia para una fecha.

    Precedencia (de mayor a menor):
        1. festivo en domingo  -> domingo_festivo
        2. festivo             -> festivo
        3. día del mes         -> dia_N (si está definido)
        4. día de la semana    -> lunes..domingo

    Devuelve None (descanso) si la ranura aplicable está vacía.
    """
    es_domingo = fecha.weekday() == 6
    if es_festivo and es_domingo and secuencia.domingo_festivo:
        return secuencia.domingo_festivo
    if es_festivo and secuencia.festivo:
        return secuencia.festivo
    codigo_dia = getattr(secuencia, f'dia_{fecha.day}')
    if codigo_dia:
        return codigo_dia
    return getattr(secuencia, _SLOTS_SEMANA[fecha.weekday()])


def aplicar_prototipo(prototipo, anio, mes, reemplazar=True):
    """
    Explota la `secuencia` de un `TurPrototipo` en filas de
    `TurProgramacionSimulacion` para un mes dado (una fila por día).

    Es el equivalente de `aplicar_secuencia` pero contra la tabla buffer de
    simulación: no toca `TurProgramacion`, no requiere contrato y las filas
    quedan libres (sin FK al prototipo ni al puesto).

    - El turno se resuelve por `codigo` contra `TurTurno`; código vacío = descanso.
    - `festivo` se marca consultando `GenFestivo`.
    - Las horas se denormalizan desde el turno resuelto.
    - Con `reemplazar=True` (por defecto) se limpia toda la tabla antes de cargar,
      tratándola como buffer de una sola corrida.

    Retorna la cantidad de filas creadas.
    """
    secuencia = prototipo.secuencia
    if secuencia is None:
        return 0

    dias_mes = calendar.monthrange(anio, mes)[1]

    festivos = set(
        GenFestivo.objects
        .filter(fecha__year=anio, fecha__month=mes)
        .values_list('fecha', flat=True)
    )

    codigos = {getattr(secuencia, campo) for campo in _CAMPOS_CODIGO if getattr(secuencia, campo)}
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}

    nuevos = []
    for dia in range(1, dias_mes + 1):
        fecha = date(anio, mes, dia)
        es_festivo = fecha in festivos
        codigo = _codigo_para_fecha(secuencia, fecha, es_festivo)
        turno = turnos.get(codigo) if codigo else None

        nuevos.append(TurProgramacionSimulacion(
            fecha=fecha,
            turno=turno,
            festivo=es_festivo,
            horas=turno.horas if turno else 0,
            horas_diurnas=turno.horas_diurnas if turno else 0,
            horas_nocturnas=turno.horas_nocturnas if turno else 0,
        ))

    with transaction.atomic():
        if reemplazar:
            TurProgramacionSimulacion.objects.all().delete()
        TurProgramacionSimulacion.objects.bulk_create(nuevos)

    return len(nuevos)
