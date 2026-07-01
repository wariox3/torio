from decimal import Decimal

from django.db import transaction
from django.db.models import F

from general.models import GenDocumento, GenDocumentoDetalle, GenFestivo
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

    total_horas = sum((p.horas for p in nuevos), Decimal('0'))
    total_diurnas = sum((p.horas_diurnas for p in nuevos), Decimal('0'))
    total_nocturnas = sum((p.horas_nocturnas for p in nuevos), Decimal('0'))

    with transaction.atomic():
        TurProgramacion.objects.bulk_create(nuevos)
        if documento_detalle is not None:
            _aplicar_delta_horas(documento_detalle, total_horas, total_diurnas, total_nocturnas)

    return len(nuevos)


def _horas_de(turno):
    """Horas (totales, diurnas, nocturnas) denormalizadas desde el turno."""
    if turno is None:
        return Decimal('0'), Decimal('0'), Decimal('0')
    return turno.horas, turno.horas_diurnas, turno.horas_nocturnas


def _aplicar_delta_horas(documento_detalle, delta_horas, delta_diurnas, delta_nocturnas):
    """Propaga un delta de horas programadas al detalle y a su documento padre."""
    if not (delta_horas or delta_diurnas or delta_nocturnas):
        return
    GenDocumentoDetalle.objects.filter(pk=documento_detalle.pk).update(
        horas_programadas=F('horas_programadas') + delta_horas,
        horas_diurnas_programadas=F('horas_diurnas_programadas') + delta_diurnas,
        horas_nocturnas_programadas=F('horas_nocturnas_programadas') + delta_nocturnas,
    )
    GenDocumento.objects.filter(pk=documento_detalle.documento_id).update(
        horas_programadas=F('horas_programadas') + delta_horas,
        horas_diurnas_programadas=F('horas_diurnas_programadas') + delta_diurnas,
        horas_nocturnas_programadas=F('horas_nocturnas_programadas') + delta_nocturnas,
    )


def actualizar_programacion(contrato, documento_detalle, items):
    """
    Sincroniza las programaciones de `(contrato, documento_detalle)` contra la
    lista deseada `items` `{fecha, turno_codigo}`, comparándola con el estado
    actual y aplicando solo las diferencias:

    - fecha nueva            -> se crea la programación (suma horas).
    - fecha ausente en items -> se elimina la programación (resta horas).
    - fecha con turno distinto -> se actualiza la fila (ajusta el delta de horas).

    Reglas iguales a `crear_programacion`: sin fechas repetidas, turnos válidos y
    `festivo` desde `GenFestivo`. Si alguna fecha nueva ya está ocupada por el
    contrato en OTRO documento_detalle, se aborta con `ProgramacionExistenteError`.
    El neto de horas se propaga a `documento_detalle` y a su documento padre.

    Retorna `{'creados', 'actualizados', 'eliminados'}`.
    """
    fechas = [item['fecha'] for item in items]

    repetidas = sorted({f.isoformat() for f in fechas if fechas.count(f) > 1})
    if repetidas:
        raise ValueError(f'Fechas repetidas en la solicitud: {repetidas}.')

    codigos = {(item.get('turno_codigo') or '').strip() for item in items}
    codigos.discard('')
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}
    faltantes = sorted(codigos - turnos.keys())
    if faltantes:
        raise ValueError(f'Turnos inexistentes: {faltantes}.')

    festivos = set(
        GenFestivo.objects.filter(fecha__in=fechas).values_list('fecha', flat=True)
    )

    existentes = {
        p.fecha: p
        for p in TurProgramacion.objects.filter(
            contrato=contrato, documento_detalle=documento_detalle
        )
    }

    fechas_nuevas = [f for f in fechas if f not in existentes]
    if fechas_nuevas:
        conflictos = list(
            TurProgramacion.objects
            .select_related('turno')
            .filter(contrato=contrato, fecha__in=fechas_nuevas)
            .exclude(documento_detalle=documento_detalle)
            .order_by('fecha')
        )
        if conflictos:
            raise ProgramacionExistenteError(conflictos)

    deseado = {}
    for item in items:
        codigo = (item.get('turno_codigo') or '').strip() or None
        deseado[item['fecha']] = turnos.get(codigo) if codigo else None

    crear = []
    actualizar = []
    eliminar_ids = []
    delta_horas = delta_diurnas = delta_nocturnas = Decimal('0')

    for fecha, turno in deseado.items():
        horas, diurnas, nocturnas = _horas_de(turno)
        actual = existentes.get(fecha)
        turno_id = turno.id if turno else None
        if actual is None:
            crear.append(TurProgramacion(
                contrato=contrato,
                fecha=fecha,
                documento_detalle=documento_detalle,
                turno=turno,
                festivo=fecha in festivos,
                horas=horas,
                horas_diurnas=diurnas,
                horas_nocturnas=nocturnas,
            ))
            delta_horas += horas
            delta_diurnas += diurnas
            delta_nocturnas += nocturnas
        elif actual.turno_id != turno_id:
            delta_horas += horas - actual.horas
            delta_diurnas += diurnas - actual.horas_diurnas
            delta_nocturnas += nocturnas - actual.horas_nocturnas
            actual.turno = turno
            actual.festivo = fecha in festivos
            actual.horas = horas
            actual.horas_diurnas = diurnas
            actual.horas_nocturnas = nocturnas
            actualizar.append(actual)

    for fecha, actual in existentes.items():
        if fecha not in deseado:
            eliminar_ids.append(actual.pk)
            delta_horas -= actual.horas
            delta_diurnas -= actual.horas_diurnas
            delta_nocturnas -= actual.horas_nocturnas

    with transaction.atomic():
        if crear:
            TurProgramacion.objects.bulk_create(crear)
        if actualizar:
            TurProgramacion.objects.bulk_update(
                actualizar,
                ['turno', 'festivo', 'horas', 'horas_diurnas', 'horas_nocturnas'],
            )
        if eliminar_ids:
            TurProgramacion.objects.filter(pk__in=eliminar_ids).delete()
        if documento_detalle is not None:
            _aplicar_delta_horas(documento_detalle, delta_horas, delta_diurnas, delta_nocturnas)

    return {
        'creados': len(crear),
        'actualizados': len(actualizar),
        'eliminados': len(eliminar_ids),
    }
