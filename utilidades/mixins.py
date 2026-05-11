"""
Mixins reutilizables para ViewSets de DRF.
"""
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action

from utilidades.filtros import aplicar_filtros, aplicar_ordenamientos

class _FiltroItemSerializer(serializers.Serializer):
    propiedad = serializers.CharField()
    operador = serializers.CharField(
        help_text='=, !=, >, >=, <, <=, contiene, comienza_con, termina_con, in, is_null',
    )
    valor = serializers.JSONField(required=False, allow_null=True)
    operador_logico = serializers.ChoiceField(choices=['AND', 'OR'], required=False)


_BusquedaRequest = inline_serializer(
    name='BusquedaRequest',
    fields={
        'filtros': _FiltroItemSerializer(many=True, required=False),
        'ordenamientos': serializers.ListField(
            child=serializers.CharField(), required=False,
            help_text='Lista de campos. Prefijo "-" para descendente.',
        ),
    },
)


class FiltrosDinamicosMixin:
    """
    Agrega la acción `POST /<recurso>/lista/` con filtros dinámicos y paginación.

    El ViewSet que lo herede debe declarar:
        campos_filtrables: set[str]                   # whitelist obligatoria

    Y opcionalmente:
        select_related_lista: tuple[str, ...]         # FKs a precargar
        prefetch_related_lista: tuple[str, ...]       # M2M / reverse a precargar
        ordenamiento_default_lista: tuple[str, ...]   # si no envían `ordenamientos`

    Para casos especiales (filtrado forzado por tenant/usuario, annotations, etc.)
    sobreescribe `get_queryset_lista`.
    """

    campos_filtrables: set = set()
    select_related_lista: tuple = ()
    prefetch_related_lista: tuple = ()
    ordenamiento_default_lista: tuple = ()

    def get_queryset_lista(self):
        qs = self.get_queryset()
        if self.select_related_lista:
            qs = qs.select_related(*self.select_related_lista)
        if self.prefetch_related_lista:
            qs = qs.prefetch_related(*self.prefetch_related_lista)
        return qs

    @extend_schema(
        summary='Listar con filtros dinámicos',
        description=(
            'Lista registros aplicando filtros dinámicos enviados en el body. '
            'Operadores soportados: =, !=, >, >=, <, <=, contiene, comienza_con, '
            'termina_con, in, is_null. Combinación AND/OR vía `operador_logico` '
            'por filtro (AND por defecto, evaluación secuencial).'
        ),
        request=_BusquedaRequest,
    )
    @action(detail=False, methods=['post'])
    def lista(self, request):
        filtros = request.data.get('filtros') or []
        ordenamientos = request.data.get('ordenamientos') or []

        qs = self.get_queryset_lista()
        qs = aplicar_filtros(qs, filtros, self.campos_filtrables)
        qs = aplicar_ordenamientos(qs, ordenamientos, self.campos_filtrables)
        if not ordenamientos and self.ordenamiento_default_lista:
            qs = qs.order_by(*self.ordenamiento_default_lista)

        pagina = self.paginate_queryset(qs)
        serializador = self.get_serializer(pagina, many=True)
        return self.get_paginated_response(serializador.data)
