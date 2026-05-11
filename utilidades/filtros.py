"""
Construye consultas Django a partir de filtros dinámicos enviados desde el cliente.

Formato esperado:

    {
        "filtros": [
            {"propiedad": "nombre_corto", "operador": "contiene", "valor": "m"},
            {"propiedad": "ciudad_id",    "operador": "!=", "valor": 1, "operador_logico": "AND"},
            {"propiedad": "telefono",     "operador": "=",  "valor": "320501", "operador_logico": "OR"}
        ],
        "ordenamientos": ["-nombre_corto"]
    }

Los filtros se evalúan de forma secuencial: cada filtro se combina con el acumulado
usando su `operador_logico` (`AND` por defecto). El primero ignora el operador lógico.
"""
from django.db.models import Q
from rest_framework.exceptions import ValidationError

_OPERADORES_SUFIJO = {
    '=':            '__exact',
    'contiene':     '__icontains',
    'comienza_con': '__istartswith',
    'termina_con':  '__iendswith',
    '>':            '__gt',
    '>=':           '__gte',
    '<':            '__lt',
    '<=':           '__lte',
    'in':           '__in',
    'is_null':      '__isnull',
}

_OPERADORES_NEGADOS = {'!='}
_OPERADORES_VALIDOS = set(_OPERADORES_SUFIJO) | _OPERADORES_NEGADOS

_OPERADORES_LOGICOS = {'AND', 'OR'}


def _construir_q(filtro: dict, campos_permitidos: set) -> Q:
    propiedad = filtro.get('propiedad')
    operador = filtro.get('operador')
    valor = filtro.get('valor')

    if not propiedad or propiedad not in campos_permitidos:
        raise ValidationError({'filtros': f'Propiedad "{propiedad}" no permitida.'})
    if operador not in _OPERADORES_VALIDOS:
        raise ValidationError({'filtros': f'Operador "{operador}" no soportado.'})

    if operador == '!=':
        return ~Q(**{f'{propiedad}__exact': valor})

    sufijo = _OPERADORES_SUFIJO[operador]
    return Q(**{f'{propiedad}{sufijo}': valor})


def aplicar_filtros(queryset, filtros: list, campos_permitidos: set):
    """Combina la lista de filtros con el queryset y devuelve el resultado filtrado."""
    if not filtros:
        return queryset

    if not isinstance(filtros, list):
        raise ValidationError({'filtros': 'Debe ser una lista.'})

    consulta = Q()
    for indice, filtro in enumerate(filtros):
        if not isinstance(filtro, dict):
            raise ValidationError({'filtros': f'El filtro #{indice} no es un objeto.'})

        q = _construir_q(filtro, campos_permitidos)

        if indice == 0:
            consulta = q
            continue

        operador_logico = (filtro.get('operador_logico') or 'AND').upper()
        if operador_logico not in _OPERADORES_LOGICOS:
            raise ValidationError(
                {'filtros': f'operador_logico "{operador_logico}" inválido (AND|OR).'}
            )

        consulta = consulta | q if operador_logico == 'OR' else consulta & q

    return queryset.filter(consulta)


def aplicar_ordenamientos(queryset, ordenamientos, campos_permitidos: set):
    """Aplica ordenamientos validando contra la lista blanca (acepta prefijo `-`)."""
    if not ordenamientos:
        return queryset

    if not isinstance(ordenamientos, list):
        raise ValidationError({'ordenamientos': 'Debe ser una lista.'})

    for campo in ordenamientos:
        nombre = campo.lstrip('-')
        if nombre not in campos_permitidos:
            raise ValidationError(
                {'ordenamientos': f'Campo "{nombre}" no permitido para ordenar.'}
            )

    return queryset.order_by(*ordenamientos)
