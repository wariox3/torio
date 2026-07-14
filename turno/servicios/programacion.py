from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from general.models import GenDocumento, GenDocumentoDetalle, GenFestivo
from turno.models import TurProgramacion, TurProgramacionSimulacion, TurTurno


class ProgramacionError(ValueError):
    """
    Errores por día al crear/actualizar programación.

    Lleva en `errores` una lista de dicts `{fecha, turno_codigo, codigo, mensaje}`
    para que la vista los devuelva junto a un `detail` general.
    """

    DETAIL = 'Hay días con errores en la programación.'

    def __init__(self, errores, detail=DETAIL):
        self.errores = errores
        self.detail = detail
        super().__init__(detail)


def _error_dia(fecha, turno_codigo, codigo, mensaje):
    return {
        'fecha': fecha.isoformat(),
        'turno_codigo': turno_codigo,
        'codigo': codigo,
        'mensaje': mensaje,
    }


def crear_programacion(contrato, documento_detalle, items):
    """
    Crea filas de `TurProgramacion` para un contrato a partir de una lista de
    items `{fecha, turno_codigo}` (fecha: `date`; turno_codigo vacío = descanso).

    - El turno se resuelve por `codigo` contra `TurTurno`.
    - Los items **sin turno** (turno_codigo vacío/null) se ignoran: no crean
      fila, así no ocupan `(contrato, fecha)` ni bloquean a otro documento_detalle.
    - `festivo` se marca consultando `GenFestivo`.
    - Las horas se denormalizan desde el turno resuelto.
    - No hay upsert: si ya existe programación para `(contrato, fecha)` —o si el
      array trae fechas repetidas, o un `turno_codigo` inexistente— se aborta
      con `ProgramacionError` (errores por día) sin guardar nada.

    Retorna la cantidad de filas creadas.
    """
    conteo = Counter(item['fecha'] for item in items)
    codigos = {(item.get('turno_codigo') or '').strip() for item in items}
    codigos.discard('')
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}

    errores = []
    repetidas_vistas = set()
    con_turno = []  # (fecha, turno, turno_codigo) de los items válidos con turno
    for item in items:
        fecha = item['fecha']
        codigo = (item.get('turno_codigo') or '').strip() or None
        if conteo[fecha] > 1:
            if fecha not in repetidas_vistas:
                repetidas_vistas.add(fecha)
                errores.append(_error_dia(
                    fecha, codigo, 'fecha_repetida', 'La fecha está repetida en la solicitud.',
                ))
            continue
        if codigo is None:
            continue  # día sin turno: se ignora, no genera fila
        turno = turnos.get(codigo)
        if turno is None:
            errores.append(_error_dia(
                fecha, codigo, 'turno_inexistente', f'El turno «{codigo}» no existe.',
            ))
            continue
        con_turno.append((fecha, turno, codigo))

    fechas_con_turno = [fecha for fecha, _, _ in con_turno]
    ocupadas = set(
        TurProgramacion.objects
        .filter(contrato=contrato, fecha__in=fechas_con_turno)
        .values_list('fecha', flat=True)
    )
    for fecha, turno, codigo in con_turno:
        if fecha in ocupadas:
            errores.append(_error_dia(
                fecha, codigo, 'dia_ocupado', 'Ya existe programación para este día.',
            ))

    if errores:
        errores.sort(key=lambda e: e['fecha'])
        raise ProgramacionError(errores)

    festivos = set(
        GenFestivo.objects.filter(fecha__in=fechas_con_turno).values_list('fecha', flat=True)
    )

    nuevos = [
        TurProgramacion(
            contrato=contrato,
            fecha=fecha,
            documento_detalle=documento_detalle,
            turno=turno,
            festivo=fecha in festivos,
            horas=turno.horas,
            horas_diurnas=turno.horas_diurnas,
            horas_nocturnas=turno.horas_nocturnas,
        )
        for fecha, turno, _ in con_turno
    ]

    total_horas = sum((p.horas for p in nuevos), Decimal('0'))
    total_diurnas = sum((p.horas_diurnas for p in nuevos), Decimal('0'))
    total_nocturnas = sum((p.horas_nocturnas for p in nuevos), Decimal('0'))

    if documento_detalle is not None:
        _validar_limite_horas(
            documento_detalle,
            (documento_detalle.horas_diurnas_programadas or Decimal('0')) + total_diurnas,
            (documento_detalle.horas_nocturnas_programadas or Decimal('0')) + total_nocturnas,
        )

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


def _validar_limite_horas(documento_detalle, diurnas_resultantes, nocturnas_resultantes):
    """
    Aborta si las horas programadas resultantes superan las planeadas del detalle
    (`horas_diurnas`/`horas_nocturnas`). Se evalúa por separado diurnas y nocturnas.
    """
    errores = []
    if diurnas_resultantes > documento_detalle.horas_diurnas:
        errores.append({
            'fecha': None,
            'turno_codigo': None,
            'codigo': 'horas_diurnas_excedidas',
            'mensaje': (
                f'Las horas diurnas programadas ({diurnas_resultantes}) superan '
                f'las planeadas del puesto ({documento_detalle.horas_diurnas}).'
            ),
        })
    if nocturnas_resultantes > documento_detalle.horas_nocturnas:
        errores.append({
            'fecha': None,
            'turno_codigo': None,
            'codigo': 'horas_nocturnas_excedidas',
            'mensaje': (
                f'Las horas nocturnas programadas ({nocturnas_resultantes}) superan '
                f'las planeadas del puesto ({documento_detalle.horas_nocturnas}).'
            ),
        })
    if errores:
        raise ProgramacionError(errores, detail='Las horas programadas superan las planeadas del puesto.')


def actualizar_programacion(contrato, documento_detalle, items):
    """
    Sincroniza las programaciones de `(contrato, documento_detalle)` contra la
    lista deseada `items` `{fecha, turno_codigo}`, comparándola con el estado
    actual y aplicando solo las diferencias:

    - fecha nueva con turno    -> se crea la programación (suma horas).
    - fecha ausente en items   -> se elimina la programación (resta horas).
    - fecha con turno distinto -> se actualiza la fila (ajusta el delta de horas).
    - fecha sin turno (descanso) -> no se persiste; si existía fila, se elimina.

    Reglas iguales a `crear_programacion`: sin fechas repetidas, turnos válidos y
    `festivo` desde `GenFestivo`. Si alguna fecha nueva con turno ya está ocupada
    por el contrato en OTRO documento_detalle, se aborta con `ProgramacionError`
    (errores por día). El neto de horas se propaga a `documento_detalle` y a su
    documento padre.

    Retorna `{'creados', 'actualizados', 'eliminados'}`.
    """
    conteo = Counter(item['fecha'] for item in items)
    codigos = {(item.get('turno_codigo') or '').strip() for item in items}
    codigos.discard('')
    turnos = {t.codigo: t for t in TurTurno.objects.filter(codigo__in=codigos)}

    existentes = {
        p.fecha: p
        for p in TurProgramacion.objects.filter(
            contrato=contrato, documento_detalle=documento_detalle
        )
    }

    errores = []
    repetidas_vistas = set()
    deseado = {}
    codigo_por_fecha = {}
    for item in items:
        fecha = item['fecha']
        codigo = (item.get('turno_codigo') or '').strip() or None
        if conteo[fecha] > 1:
            if fecha not in repetidas_vistas:
                repetidas_vistas.add(fecha)
                errores.append(_error_dia(
                    fecha, codigo, 'fecha_repetida', 'La fecha está repetida en la solicitud.',
                ))
            continue
        if codigo is None:
            deseado[fecha] = None
            continue
        turno = turnos.get(codigo)
        if turno is None:
            errores.append(_error_dia(
                fecha, codigo, 'turno_inexistente', f'El turno «{codigo}» no existe.',
            ))
            continue
        deseado[fecha] = turno
        codigo_por_fecha[fecha] = codigo

    # Fechas con turno que aún no existen en este detalle: pueden chocar con otro
    # documento_detalle del mismo contrato.
    fechas_a_crear = [
        fecha for fecha, turno in deseado.items()
        if turno is not None and fecha not in existentes
    ]
    ocupadas = (
        TurProgramacion.objects
        .filter(contrato=contrato, fecha__in=fechas_a_crear)
        .exclude(documento_detalle=documento_detalle)
        .values_list('fecha', flat=True)
    )
    for fecha in ocupadas:
        errores.append(_error_dia(
            fecha, codigo_por_fecha.get(fecha), 'dia_ocupado',
            'Ya existe programación para este día.',
        ))

    if errores:
        errores.sort(key=lambda e: e['fecha'])
        raise ProgramacionError(errores)

    festivos = set(
        GenFestivo.objects.filter(fecha__in=deseado).values_list('fecha', flat=True)
    )

    crear = []
    actualizar = []
    eliminar_ids = []
    delta_horas = delta_diurnas = delta_nocturnas = Decimal('0')

    for fecha, turno in deseado.items():
        actual = existentes.get(fecha)
        if turno is None:
            # Día sin turno: no se persiste; si había fila, se elimina.
            if actual is not None:
                eliminar_ids.append(actual.pk)
                delta_horas -= actual.horas
                delta_diurnas -= actual.horas_diurnas
                delta_nocturnas -= actual.horas_nocturnas
            continue
        horas, diurnas, nocturnas = _horas_de(turno)
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
        elif actual.turno_id != turno.id:
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

    if documento_detalle is not None:
        _validar_limite_horas(
            documento_detalle,
            (documento_detalle.horas_diurnas_programadas or Decimal('0')) + delta_diurnas,
            (documento_detalle.horas_nocturnas_programadas or Decimal('0')) + delta_nocturnas,
        )

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


def generar_programacion(documento_detalle):
    """
    Materializa el buffer de `TurProgramacionSimulacion` en `TurProgramacion`.

    `documento_detalle` es el **destino**: las programaciones creadas cuelgan de él,
    sus horas se le suman (a él y a su documento padre) y es el que se marca como
    `generado`. La simulación, en cambio, se lee del **origen**, que es su
    `documento_detalle_afectado` (donde viven los prototipos).

    - Las filas simuladas **sin turno** (descanso) se ignoran: no crean fila, así
      no ocupan `(contrato, fecha)` ni bloquean a otro documento_detalle.
    - Aborta con `ProgramacionError` si alguna fila simulada no tiene contrato, si
      el contrato no está habilitado para turnos, si el par `(contrato, fecha)` ya
      está programado, o si las horas resultantes superan las planeadas del destino.
    - Las horas y `festivo` se toman de la simulación (es lo que el usuario vio en
      la grilla).
    - Al terminar marca `documento_detalle.generado` y vacía el buffer completo.

    Retorna la cantidad de filas creadas.
    """
    if documento_detalle.generado:
        raise ProgramacionError(
            [], detail='El documento detalle ya fue generado.',
        )

    if documento_detalle.documento_detalle_afectado_id is None:
        raise ProgramacionError(
            [], detail='El documento detalle no tiene documento detalle afectado.',
        )

    simulaciones = list(
        TurProgramacionSimulacion.objects
        .filter(documento_detalle_id=documento_detalle.documento_detalle_afectado_id)
        .select_related('contrato', 'turno')
        .order_by('fecha', 'id')
    )
    if not simulaciones:
        raise ProgramacionError([], detail='No hay simulación para generar.')

    # Los días de descanso (sin turno) no se materializan.
    con_turno = [s for s in simulaciones if s.turno_id is not None]
    if not con_turno:
        raise ProgramacionError([], detail='La simulación no tiene días con turno.')

    errores = []

    sin_contrato = [s for s in con_turno if s.contrato_id is None]
    for s in sin_contrato:
        errores.append(_error_dia(
            s.fecha, s.turno.codigo, 'sin_contrato',
            'La simulación no tiene contrato asignado.',
        ))

    contratos = {s.contrato_id: s.contrato for s in con_turno if s.contrato_id is not None}
    for contrato in contratos.values():
        if not contrato.habilitado_turno:
            errores.append({
                'fecha': None,
                'turno_codigo': None,
                'codigo': 'contrato_no_habilitado',
                'mensaje': f'El contrato {contrato.id} no está habilitado para turnos.',
            })

    # El unique es (contrato, fecha) global: el día puede estar ocupado por otro puesto.
    ocupadas = set(
        TurProgramacion.objects
        .filter(
            contrato_id__in=contratos,
            fecha__in={s.fecha for s in con_turno},
        )
        .values_list('contrato_id', 'fecha')
    )
    for s in con_turno:
        if (s.contrato_id, s.fecha) in ocupadas:
            errores.append(_error_dia(
                s.fecha, s.turno.codigo, 'dia_ocupado',
                'Ya existe programación para este día.',
            ))

    if errores:
        errores.sort(key=lambda e: (e['fecha'] or ''))
        raise ProgramacionError(errores)

    nuevos = [
        TurProgramacion(
            contrato_id=s.contrato_id,
            fecha=s.fecha,
            documento_detalle=documento_detalle,
            turno_id=s.turno_id,
            festivo=s.festivo,
            horas=s.horas,
            horas_diurnas=s.horas_diurnas,
            horas_nocturnas=s.horas_nocturnas,
        )
        for s in con_turno
    ]

    total_horas = sum((p.horas for p in nuevos), Decimal('0'))
    total_diurnas = sum((p.horas_diurnas for p in nuevos), Decimal('0'))
    total_nocturnas = sum((p.horas_nocturnas for p in nuevos), Decimal('0'))

    _validar_limite_horas(
        documento_detalle,
        (documento_detalle.horas_diurnas_programadas or Decimal('0')) + total_diurnas,
        (documento_detalle.horas_nocturnas_programadas or Decimal('0')) + total_nocturnas,
    )

    with transaction.atomic():
        TurProgramacion.objects.bulk_create(nuevos)
        _aplicar_delta_horas(documento_detalle, total_horas, total_diurnas, total_nocturnas)
        GenDocumentoDetalle.objects.filter(pk=documento_detalle.pk).update(generado=True)
        TurProgramacionSimulacion.objects.all().delete()

    return len(nuevos)


def desgenerar_programacion(documento_detalle):
    """
    Revierte `generar_programacion`: borra todas las programaciones que cuelgan del
    `documento_detalle` (de todos sus contratos), descuenta sus horas del detalle y
    de su documento padre, y lo desmarca como `generado`.

    No repuebla el buffer de simulación: para volver a generar hay que simular de nuevo.

    Retorna la cantidad de filas eliminadas.
    """
    if not documento_detalle.generado:
        raise ProgramacionError(
            [], detail='El documento detalle no ha sido generado.',
        )

    qs = TurProgramacion.objects.filter(documento_detalle=documento_detalle)
    agregados = qs.aggregate(
        horas=Sum('horas'),
        horas_diurnas=Sum('horas_diurnas'),
        horas_nocturnas=Sum('horas_nocturnas'),
    )

    with transaction.atomic():
        eliminados, _ = qs.delete()
        _aplicar_delta_horas(
            documento_detalle,
            -(agregados['horas'] or Decimal('0')),
            -(agregados['horas_diurnas'] or Decimal('0')),
            -(agregados['horas_nocturnas'] or Decimal('0')),
        )
        GenDocumentoDetalle.objects.filter(pk=documento_detalle.pk).update(generado=False)

    return eliminados


def eliminar_programaciones(contrato_id, documento_detalle_id):
    """
    Borra todas las programaciones de un `(contrato, documento_detalle)` y descuenta
    sus horas del detalle y de su documento padre. Retorna cuántas eliminó.

    Debe llamarse dentro de una transacción (lo hacen las vistas).
    """
    qs = TurProgramacion.objects.filter(
        contrato_id=contrato_id, documento_detalle_id=documento_detalle_id
    )
    agregados = qs.aggregate(
        horas=Sum('horas'),
        horas_diurnas=Sum('horas_diurnas'),
        horas_nocturnas=Sum('horas_nocturnas'),
    )
    eliminados, _ = qs.delete()
    if not eliminados:
        return 0

    total_horas = agregados['horas'] or Decimal('0')
    total_diurnas = agregados['horas_diurnas'] or Decimal('0')
    total_nocturnas = agregados['horas_nocturnas'] or Decimal('0')
    GenDocumentoDetalle.objects.filter(pk=documento_detalle_id).update(
        horas_programadas=F('horas_programadas') - total_horas,
        horas_diurnas_programadas=F('horas_diurnas_programadas') - total_diurnas,
        horas_nocturnas_programadas=F('horas_nocturnas_programadas') - total_nocturnas,
    )
    GenDocumento.objects.filter(
        documentos_detalles_documento_rel__pk=documento_detalle_id
    ).update(
        horas_programadas=F('horas_programadas') - total_horas,
        horas_diurnas_programadas=F('horas_diurnas_programadas') - total_diurnas,
        horas_nocturnas_programadas=F('horas_nocturnas_programadas') - total_nocturnas,
    )
    return eliminados
