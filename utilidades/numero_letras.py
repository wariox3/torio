"""
Un número en palabras, en español.

Hace falta para los documentos que se firman —un egreso, un cheque—, donde el
importe va también en letras para que no se pueda alterar una cifra sin que se
note. El proyecto no tenía nada parecido y no se agregó una dependencia por
cincuenta líneas: `num2words` traería veinte idiomas y sus reglas para usar una.

Las tres trampas del español, que es donde fallan las implementaciones ingenuas:

- **Apócope**: «veintiún mil», no «veintiuno mil»; «un millón», no «uno millón».
- **Cientos**: «cien» solo cuando es exacto; «ciento uno» en cualquier otro caso.
- **Plural de millón**: «un millón» pero «dos millones», y «mil» nunca pluraliza.
"""
from decimal import Decimal

_UNIDADES = (
    '', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho',
    'nueve', 'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis',
    'diecisiete', 'dieciocho', 'diecinueve', 'veinte', 'veintiuno',
    'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco', 'veintiséis',
    'veintisiete', 'veintiocho', 'veintinueve',
)
_DECENAS = (
    '', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta',
    'ochenta', 'noventa',
)
_CENTENAS = (
    '', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos',
    'seiscientos', 'setecientos', 'ochocientos', 'novecientos',
)


def _hasta_cien(numero):
    if numero < 30:
        return _UNIDADES[numero]
    decena, unidad = divmod(numero, 10)
    if unidad == 0:
        return _DECENAS[decena]
    return f'{_DECENAS[decena]} y {_UNIDADES[unidad]}'


def _hasta_mil(numero):
    """0-999. «cien» exacto, «ciento» acompañado."""
    if numero == 100:
        return 'cien'
    centena, resto = divmod(numero, 100)
    palabras = _CENTENAS[centena]
    if resto == 0:
        return palabras
    return f'{palabras} {_hasta_cien(resto)}'.strip()


def _apocope(texto):
    """«veintiuno» -> «veintiún», «uno» -> «un», delante de un sustantivo."""
    if texto == 'uno':
        return 'un'
    if texto.endswith('veintiuno'):
        return f'{texto[:-len("veintiuno")]}veintiún'
    if texto.endswith(' uno'):
        return f'{texto[:-4]} un'
    return texto


def _grupo(numero, singular, plural):
    """Un bloque de miles o de millones, con su apócope y su plural."""
    if numero == 0:
        return ''
    if numero == 1:
        return singular
    return f'{_apocope(_hasta_mil(numero))} {plural}'


def numero_a_letras(numero):
    """
    El entero en palabras, en minúsculas. `0` es «cero».

    Cubre hasta billones, que es más de lo que cabe en un
    `DecimalField(max_digits=20, decimal_places=6)`.
    """
    numero = int(numero)
    if numero < 0:
        return f'menos {numero_a_letras(-numero)}'
    if numero == 0:
        return 'cero'

    partes = []
    billones, resto = divmod(numero, 10**12)
    millones, resto = divmod(resto, 10**6)
    miles, unidades = divmod(resto, 1000)

    if billones:
        partes.append(_grupo(billones, 'un billón', 'billones'))
    if millones:
        partes.append(_grupo(millones, 'un millón', 'millones'))
    if miles:
        # «mil» nunca pluraliza: «dos mil», no «dos miles».
        partes.append('mil' if miles == 1 else f'{_apocope(_hasta_mil(miles))} mil')
    if unidades:
        partes.append(_hasta_mil(unidades))

    return ' '.join(parte for parte in partes if parte)


def valor_en_letras(valor, moneda='PESOS M/L'):
    """
    El importe como se escribe en un documento que se firma.

    Los centavos se descartan: un egreso se gira por pesos enteros y el original
    tampoco los ponía. Se redondea, no se trunca, para que las letras no
    contradigan la cifra impresa al lado.
    """
    entero = int(Decimal(valor or 0).quantize(Decimal('1')))
    return f'{numero_a_letras(entero).upper()} {moneda}'.strip()
