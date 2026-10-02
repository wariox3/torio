import calendar


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
