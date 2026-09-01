"""
Normalización y validación de teléfonos en formato E.164 (`+573001234567`).

Se guarda el número canónico —indicativo incluido, sin espacios ni separadores— en
una sola columna. Es lo que piden las APIs de mensajería y lo que permite comparar
dos números escritos distinto sin adivinar nada.

Deliberadamente **no** se usa `phonenumbers`: aquí solo se valida la forma general
que exige la ITU-T E.164 (un indicativo que no empieza en 0, entre 7 y 15 dígitos en
total) más la longitud nacional de los países que nos importa validar de verdad, en
`LONGITUDES_NACIONALES`. La consecuencia hay que tenerla clara: un número bien
formado pero inexistente pasa la validación. La única prueba real de que un número
existe es mandarle un código y ver si llega.
"""

import re

from rest_framework import serializers

# País asumido cuando el número llega sin indicativo. Un número internacional tiene
# que venir con `+` (o con el prefijo `00`): sin él es imposible distinguir un
# indicativo de los primeros dígitos del número nacional.
INDICATIVO_POR_DEFECTO = '57'

# E.164 fija el máximo en 15 dígitos contando el indicativo. El mínimo no está
# normalizado; 7 es el largo total de los países más pequeños (p. ej. +290 de Santa
# Elena), así que por debajo de eso no hay número posible en ninguna parte.
LONGITUD_TOTAL_MINIMA = 7
LONGITUD_TOTAL_MAXIMA = 15

# Largo del número nacional para los países cuyo formato sí validamos. El resto del
# mundo pasa solo con la validación genérica de arriba. Agregar un país aquí es la
# forma de endurecer la validación cuando empiece a importar.
LONGITUDES_NACIONALES = {
    '57': (10,),  # Colombia
}

MENSAJE_INVALIDO = (
    'Ingresa un número válido con indicativo internacional, por ejemplo +573001234567.'
)

_SEPARADORES = re.compile(r'[\s\-.()/]')


def normalizar_e164(valor: str | None, indicativo_por_defecto: str = INDICATIVO_POR_DEFECTO) -> str | None:
    """
    Devuelve el número en E.164, o None si no es un número posible.

    Acepta la entrada sucia que manda cualquier formulario: espacios, guiones,
    paréntesis, el prefijo internacional `00` y el `+`. Un valor sin `+` se toma como
    número nacional del país por defecto.
    """
    if valor is None:
        return None

    texto = _SEPARADORES.sub('', str(valor).strip())
    if not texto:
        return None

    if texto.startswith('00'):
        # Prefijo de salida internacional que se usa en buena parte del mundo.
        digitos = texto[2:]
    elif texto.startswith('+'):
        digitos = texto[1:]
    else:
        # Nacional: se le quita el 0 de larga distancia con el que en varios países
        # se escribe el número dentro de sus fronteras (07911… en Reino Unido).
        digitos = indicativo_por_defecto + texto.lstrip('0')

    if not digitos.isdigit():
        return None
    if digitos.startswith('0'):
        # Ningún indicativo de país empieza en 0.
        return None
    if not LONGITUD_TOTAL_MINIMA <= len(digitos) <= LONGITUD_TOTAL_MAXIMA:
        return None
    if not _longitud_nacional_valida(digitos):
        return None

    return f'+{digitos}'


def a_nacional(valor: str | None, indicativo: str = INDICATIVO_POR_DEFECTO) -> str | None:
    """
    Número nacional, sin indicativo, para los proveedores que lo exigen así.

    None si el número no es de ese país —que es la respuesta correcta cuando a ese
    destino no se le puede enviar— o si no es un número válido. Acepta también los
    valores viejos guardados sin indicativo, que se leen como nacionales.
    """
    e164 = normalizar_e164(valor, indicativo)
    if e164 is None:
        return None

    digitos = e164[1:]
    if not digitos.startswith(indicativo):
        return None
    return digitos[len(indicativo):]


def _longitud_nacional_valida(digitos: str) -> bool:
    for indicativo, longitudes in LONGITUDES_NACIONALES.items():
        if digitos.startswith(indicativo):
            return len(digitos) - len(indicativo) in longitudes
    return True


def normalizar_para_importar(valor, etiqueta: str = 'Celular') -> str | None:
    """
    Normaliza el teléfono de una celda de Excel, para los importadores.

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
