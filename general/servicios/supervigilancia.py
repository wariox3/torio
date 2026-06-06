from datetime import time
from decimal import Decimal


class LiquidadorSupervigilancia:
    """
    Cálculo de la tarifa mínima de servicios de vigilancia según las reglas de
    SuperVigilancia. Lógica de dominio stateless: recibe los datos por parámetro
    y no toca la base de datos.
    """

    # Frontera legal jornada diurna (Ley 2101 de 2021): diurno [06:00, 19:00), nocturno el resto.
    FRONTERA_DIURNA_INICIO = time(6, 0)
    FRONTERA_DIURNA_FIN = time(19, 0)
    # Reparto del valor mensual entre franja diurna y nocturna (suman 100%).
    PORCENTAJE_DIURNO = Decimal('47.59')
    PORCENTAJE_NOCTURNO = Decimal('52.41')
    DIAS_MES = Decimal('30')
    HORAS_DIURNAS_DIA = Decimal('13')
    HORAS_NOCTURNAS_DIA = Decimal('11')
    SEMANAS_MES = 4  # periodo mensual: cada día de la semana se repite 4 veces

    @classmethod
    def particionar_horas(cls, hora_desde, hora_hasta):
        """
        Reparte un turno [hora_desde, hora_hasta] en horas diurnas y nocturnas
        según la frontera legal. Soporta turnos que cruzan la medianoche.
        Retorna (horas_diurnas, horas_nocturnas) como Decimal.
        """
        inicio = hora_desde.hour * 60 + hora_desde.minute
        fin = hora_hasta.hour * 60 + hora_hasta.minute
        if fin <= inicio:
            fin += 24 * 60  # el turno cruza la medianoche

        diurno_inicio = cls.FRONTERA_DIURNA_INICIO.hour * 60 + cls.FRONTERA_DIURNA_INICIO.minute
        diurno_fin = cls.FRONTERA_DIURNA_FIN.hour * 60 + cls.FRONTERA_DIURNA_FIN.minute

        minutos_diurnos = 0
        for minuto in range(inicio, fin):
            if diurno_inicio <= (minuto % (24 * 60)) < diurno_fin:
                minutos_diurnos += 1
        minutos_nocturnos = (fin - inicio) - minutos_diurnos

        return Decimal(minutos_diurnos) / 60, Decimal(minutos_nocturnos) / 60

    @classmethod
    def calcular_precio(
        cls, *, salario, hora_desde, hora_hasta, sector, modalidad, precio_adicional=Decimal('0'),
        lunes=False, martes=False, miercoles=False, jueves=False, viernes=False,
        sabado=False, domingo=False, festivo=False,
    ):
        """
        Calcula la tarifa mínima de un servicio de vigilancia (periodo mensual).
        Devuelve el desglose de horas, valores hora y el precio mínimo.
        """
        horas_diurnas_unidad, horas_nocturnas_unidad = cls.particionar_horas(hora_desde, hora_hasta)

        # Días del mes según los días marcados (cada uno se repite SEMANAS_MES veces)
        dias_ordinarios = cls.SEMANAS_MES * sum((lunes, martes, miercoles, jueves, viernes))
        dias_sabados = cls.SEMANAS_MES if sabado else 0
        dias_dominicales = cls.SEMANAS_MES if domingo else 0
        dias_festivos = 2 if festivo else 0
        total_dias = dias_ordinarios + dias_sabados + dias_dominicales + dias_festivos

        horas_diurnas = horas_diurnas_unidad * total_dias
        horas_nocturnas = horas_nocturnas_unidad * total_dias

        # Valor base según sector y modalidad
        valor_base_servicio = (salario * sector.porcentaje) + precio_adicional
        if sector.tipo == 'R':  # residencial
            porcentaje_modalidad = modalidad.porcentaje_residencial
        else:  # comercial
            porcentaje_modalidad = modalidad.porcentaje_comercial
        valor_base_servicio_mes = valor_base_servicio + (valor_base_servicio * porcentaje_modalidad / 100)

        # Valor de la hora por franja
        valor_hora_diurna = (
            valor_base_servicio_mes * cls.PORCENTAJE_DIURNO / 100 / cls.DIAS_MES / cls.HORAS_DIURNAS_DIA
        )
        valor_hora_nocturna = (
            valor_base_servicio_mes * cls.PORCENTAJE_NOCTURNO / 100 / cls.DIAS_MES / cls.HORAS_NOCTURNAS_DIA
        )

        precio_minimo = (horas_diurnas * valor_hora_diurna) + (horas_nocturnas * valor_hora_nocturna)

        centavos = Decimal('0.01')
        return {
            'horas_diurnas_unidad': horas_diurnas_unidad.quantize(centavos),
            'horas_nocturnas_unidad': horas_nocturnas_unidad.quantize(centavos),
            'total_dias': total_dias,
            'horas_diurnas': horas_diurnas.quantize(centavos),
            'horas_nocturnas': horas_nocturnas.quantize(centavos),
            'valor_hora_diurna': valor_hora_diurna.quantize(centavos),
            'valor_hora_nocturna': valor_hora_nocturna.quantize(centavos),
            'precio_minimo': precio_minimo.quantize(centavos),
        }
