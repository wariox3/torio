"""
Normalización y validación de celulares en formato E.164 (`+573001234567`).

Se guarda el número canónico —indicativo incluido, sin espacios ni separadores— en
una sola columna. Es lo que piden las APIs de mensajería y lo que permite comparar
dos números escritos distinto sin adivinar nada.

**El indicativo es obligatorio y no se asume ninguno.** Sin `+` (o el prefijo de
salida `00`) es imposible distinguir un indicativo del arranque del número nacional:
un móvil mexicano de diez dígitos escrito sin `+52` se guardaría como un colombiano
que no existe. Antes se asumía Colombia y ese era justamente el agujero; ahora un
número sin prefijo se rechaza y el front tiene que mandarlo completo.

Deliberadamente **no** se usa `phonenumbers`. Lo que se valida es: que el indicativo
esté asignado (`INDICATIVOS`), que el total quepa en los quince dígitos de la
ITU-T E.164, y el largo nacional de los países de `LONGITUDES_NACIONALES`. La
consecuencia hay que tenerla clara: un número bien formado pero inexistente pasa la
validación. La única prueba real de que un número existe es mandarle un código.
"""

import re

from rest_framework import serializers

# Indicativo de Colombia. No es un valor por defecto para interpretar la entrada:
# es el país al que Zinc entrega SMS, y `a_nacional()` lo usa para saber si un
# número le sirve o no.
INDICATIVO_COLOMBIA = '57'

# E.164 fija el máximo en 15 dígitos contando el indicativo. El mínimo no está
# normalizado; 7 es el largo total de los países más pequeños (p. ej. +290 de Santa
# Elena), así que por debajo de eso no hay número posible en ninguna parte.
LONGITUD_TOTAL_MINIMA = 7
LONGITUD_TOTAL_MAXIMA = 15

# Largo del número nacional para los países cuyo formato sí validamos. El resto del
# mundo pasa solo con la validación genérica. Agregar un país aquí es la forma de
# endurecer la validación cuando empiece a importar.
LONGITUDES_NACIONALES = {
    INDICATIVO_COLOMBIA: (10,),
}

# Indicativos de país asignados por la ITU-T. El conjunto es libre de prefijos
# —ningún indicativo asignado es prefijo de otro—, así que `_indicativo_de()` puede
# probar largos de 1 a 3 y encontrar como mucho una coincidencia.
#
# No se incluyen los rangos no geográficos (800 de cobro revertido internacional,
# 87x/88x satelitales): no son números a los que se le mande un SMS a una persona.
INDICATIVOS = {
    '1', '7',
    '20', '27',
    '30', '31', '32', '33', '34', '36', '39',
    '40', '41', '43', '44', '45', '46', '47', '48', '49',
    '51', '52', '53', '54', '55', '56', '57', '58',
    '60', '61', '62', '63', '64', '65', '66',
    '81', '82', '84', '86',
    '90', '91', '92', '93', '94', '95', '98',
    '211', '212', '213', '216', '218',
    '220', '221', '222', '223', '224', '225', '226', '227', '228', '229',
    '230', '231', '232', '233', '234', '235', '236', '237', '238', '239',
    '240', '241', '242', '243', '244', '245', '246', '247', '248', '249',
    '250', '251', '252', '253', '254', '255', '256', '257', '258',
    '260', '261', '262', '263', '264', '265', '266', '267', '268', '269',
    '290', '291', '297', '298', '299',
    '350', '351', '352', '353', '354', '355', '356', '357', '358', '359',
    '370', '371', '372', '373', '374', '375', '376', '377', '378', '379',
    '380', '381', '382', '383', '385', '386', '387', '389',
    '420', '421', '423',
    '500', '501', '502', '503', '504', '505', '506', '507', '508', '509',
    '590', '591', '592', '593', '594', '595', '596', '597', '598', '599',
    '670', '672', '673', '674', '675', '676', '677', '678', '679',
    '680', '681', '682', '683', '685', '686', '687', '688', '689',
    '690', '691', '692',
    '850', '852', '853', '855', '856',
    '880', '886',
    '960', '961', '962', '963', '964', '965', '966', '967', '968',
    '970', '971', '972', '973', '974', '975', '976', '977',
    '992', '993', '994', '995', '996', '998',
}

MENSAJE_INVALIDO = (
    'Ingresa el celular con indicativo del país, por ejemplo +573001234567.'
)

_SEPARADORES = re.compile(r'[\s\-.()/]')


def normalizar_e164(valor: str | None) -> str | None:
    """
    Devuelve el número en E.164, o None si no es un número posible.

    Acepta la entrada sucia que manda cualquier formulario —espacios, guiones,
    paréntesis— pero exige el indicativo: o `+57…`, o el prefijo de salida `0057…`.
    Un número sin prefijo se rechaza; no se asume país.
    """
    if valor is None:
        return None

    texto = _SEPARADORES.sub('', str(valor).strip())
    if texto.startswith('00'):
        # Prefijo de salida internacional que se usa en buena parte del mundo.
        digitos = texto[2:]
    elif texto.startswith('+'):
        digitos = texto[1:]
    else:
        return None

    if not digitos.isdigit():
        return None
    if not LONGITUD_TOTAL_MINIMA <= len(digitos) <= LONGITUD_TOTAL_MAXIMA:
        return None

    indicativo = _indicativo_de(digitos)
    if indicativo is None:
        return None

    longitudes = LONGITUDES_NACIONALES.get(indicativo)
    if longitudes is not None and len(digitos) - len(indicativo) not in longitudes:
        return None

    return f'+{digitos}'


def a_nacional(valor: str | None, indicativo: str = INDICATIVO_COLOMBIA) -> str | None:
    """
    Número nacional, sin indicativo, para los proveedores que lo exigen así.

    None si el número no es de ese país —que es la respuesta correcta cuando a ese
    destino no se le puede enviar— o si no es válido.
    """
    e164 = normalizar_e164(valor)
    if e164 is None:
        return None

    digitos = e164[1:]
    if not digitos.startswith(indicativo):
        return None
    return digitos[len(indicativo):]


def _indicativo_de(digitos: str) -> str | None:
    for largo in (1, 2, 3):
        if digitos[:largo] in INDICATIVOS:
            return digitos[:largo]
    return None


def normalizar_para_importar(valor, etiqueta: str = 'Celular') -> str | None:
    """
    Normaliza el celular de una celda de Excel, para los importadores.

    Devuelve None cuando la celda viene vacía —cada importador sabe si su campo
    guarda `''` o `None`— y lanza `ValueError` con el mensaje que el mixin muestra
    fila por fila cuando trae algo que no es un número.
    """
    texto = '' if valor is None else str(valor).strip()
    if not texto:
        return None

    e164 = normalizar_e164(texto)
    if e164 is None:
        raise ValueError(f'{etiqueta} no es válido: "{texto}". {MENSAJE_INVALIDO}')
    return e164


class CampoTelefono(serializers.CharField):
    """
    Campo de serializer que guarda siempre E.164, venga como venga del front.

    La normalización va en `to_internal_value` a propósito: así lo que entra a la
    base ya es canónico y ningún consumidor tiene que volver a adivinar el formato.
    """

    def to_internal_value(self, data):
        texto = super().to_internal_value(data)
        e164 = normalizar_e164(texto)
        if e164 is None:
            raise serializers.ValidationError(MENSAJE_INVALIDO)
        return e164
