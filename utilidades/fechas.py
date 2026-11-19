import calendar
from datetime import date


def dias_prestacionales(fecha_desde, fecha_hasta):
    """
    Días entre dos fechas, ambas incluidas, en la convención 30/360: todo mes
    tiene 30 días, así que el 31 cuenta como 30 y un año completo da 360. Si el
    periodo termina el último día de febrero, también cuenta como 30.
    """
    dia_desde = min(fecha_desde.day, 30)
    dia_hasta = min(fecha_hasta.day, 30)
    if fecha_hasta.month == 2 and fecha_hasta.day == calendar.monthrange(fecha_hasta.year, 2)[1]:
        dia_hasta = 30
    meses = (fecha_hasta.year - fecha_desde.year) * 12 + fecha_hasta.month - fecha_desde.month
    return meses * 30 + dia_hasta - dia_desde + 1


def sumar_dias_prestacionales(fecha_desde, dias):
    """
    La fecha hasta la que un periodo que empieza en `fecha_desde` cubre `dias`
    días 30/360, ambas incluidas: la inversa de `dias_prestacionales`.

    Cuando el periodo cierra el día 30 comercial se devuelve el último día real
    del mes —el 31, o el 28/29 de febrero—, que `dias_prestacionales` cuenta como
    30. Así un año desde el 1 de marzo cierra el último día de febrero, y el
    periodo siguiente arranca el día 1 sin pisarse.
    """
    if dias < 1:
        raise ValueError('Un periodo cubre al menos un día.')
    ordinal = (fecha_desde.year * 12 + fecha_desde.month - 1) * 30 + min(fecha_desde.day, 30) - 1
    meses, dia = divmod(ordinal + dias - 1, 30)
    anio, mes = divmod(meses, 12)
    mes += 1
    ultimo = calendar.monthrange(anio, mes)[1]
    dia = ultimo if dia == 29 else min(dia + 1, ultimo)
    return date(anio, mes, dia)
