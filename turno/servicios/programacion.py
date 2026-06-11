import calendar
from datetime import date

from django.db import transaction

from general.models import GenFestivo
from turno.models import TurProgramacion, TurTurno

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


def aplicar_secuencia(secuencia, contrato, anio, mes, documento_detalle=None):
    """
    Explota una `TurSecuencia` en filas de `TurProgramacion` para un contrato
    en un mes dado (una fila por día, upsert sobre (contrato, fecha)).

    - El turno se resuelve por `codigo` contra `TurTurno`; código vacío = descanso.
    - `festivo` se marca consultando `GenFestivo`.
    - Las horas se denormalizan desde el turno resuelto.

    Retorna (creados, actualizados).
    """
    dias_mes = calendar.monthrange(anio, mes)[1]

    festivos = set(
        GenFestivo.objects
        .filter(fecha__year=anio, fecha__month=mes)
        .values_list('fecha', flat=True)
    )

    codigos = {getattr(secuencia, campo) for campo in _CAMPOS_CODIGO if getattr(secuencia, campo)}
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}

    creados = 0
    actualizados = 0
    with transaction.atomic():
        for dia in range(1, dias_mes + 1):
            fecha = date(anio, mes, dia)
            es_festivo = fecha in festivos
            codigo = _codigo_para_fecha(secuencia, fecha, es_festivo)
            turno = turnos.get(codigo) if codigo else None

            defaults = {
                'turno': turno,
                'documento_detalle': documento_detalle,
                'festivo': es_festivo,
                'horas': turno.horas if turno else 0,
                'horas_diurnas': turno.horas_diurnas if turno else 0,
                'horas_nocturnas': turno.horas_nocturnas if turno else 0,
            }
            _, creado = TurProgramacion.objects.update_or_create(
                contrato=contrato,
                fecha=fecha,
                defaults=defaults,
            )
            if creado:
                creados += 1
            else:
                actualizados += 1

    return creados, actualizados
