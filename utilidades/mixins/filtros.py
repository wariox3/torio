"""
Mixin de filtros dinámicos para ViewSets de DRF.
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


# Usado por `FiltrosDinamicosMixin.lista` y `ExportarExcelMixin.excel`.
BusquedaRequest = inline_serializer(
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

    La configuración puede declararse en el ViewSet o (preferido) en su serializer:
        campos_filtrables: set[str]                   # whitelist obligatoria
        select_related_lista: tuple[str, ...]         # FKs a precargar
        prefetch_related_lista: tuple[str, ...]       # M2M / reverse a precargar
        ordenamiento_default_lista: tuple[str, ...]   # si no envían `ordenamientos`

    Se busca primero en `serializer_class`; si no existe el atributo, cae al
    ViewSet. Para casos especiales (filtrado forzado por tenant/usuario,
    annotations, etc.) sobreescribe `get_queryset_lista`.
    """

    def _config_lista(self, name, default):
        serializer_cls = self.get_serializer_class()
        if hasattr(serializer_cls, name):
            return getattr(serializer_cls, name)
        return getattr(self, name, default)

    def get_queryset_lista(self):
        qs = self.get_queryset()
        select = self._config_lista('select_related_lista', ())
        prefetch = self._config_lista('prefetch_related_lista', ())
        if select:
            qs = qs.select_related(*select)
        if prefetch:
            qs = qs.prefetch_related(*prefetch)
        return qs

    @extend_schema(
        summary='Listar con filtros dinámicos',
        description=(
            'Lista registros aplicando filtros dinámicos enviados en el body. '
            'Operadores soportados: =, !=, >, >=, <, <=, contiene, comienza_con, '
            'termina_con, in, is_null. Combinación AND/OR vía `operador_logico` '
            'por filtro (AND por defecto, evaluación secuencial).'
        ),
        request=BusquedaRequest,
    )
    @action(detail=False, methods=['post'])
    def lista(self, request):
        filtros = request.data.get('filtros') or []
        ordenamientos = request.data.get('ordenamientos') or []

        campos_filtrables = self._config_lista('campos_filtrables', set())
        qs = self.get_queryset_lista()
        qs = aplicar_filtros(qs, filtros, campos_filtrables)
        qs = aplicar_ordenamientos(qs, ordenamientos, campos_filtrables)
        if not ordenamientos:
            default = self._config_lista('ordenamiento_default_lista', ())
            if default:
                qs = qs.order_by(*default)

        pagina = self.paginate_queryset(qs)
        serializador = self.get_serializer(pagina, many=True)
        return self.get_paginated_response(serializador.data)
