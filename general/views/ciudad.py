from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from general.models import GenCiudad
from general.serializers import GenCiudadSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('id', int, description='Filtrar por ID de ciudad'),
    OpenApiParameter('estado', int, description='Filtrar por ID de estado'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Ciudad'])
class GenCiudadViewSet(viewsets.GenericViewSet):
    serializer_class = GenCiudadSeleccionarSerializer

    @extend_schema(
        description=(
            'Lista de ciudades para un selector. `id` sirve para resolver una '
            'ciudad ya guardada —el `gen_empresa_ciudad` de la configuración, '
            'por ejemplo— sin tener que recorrer la lista completa buscándola.'
        ),
        parameters=_SELECCIONAR_PARAMS,
        responses=GenCiudadSeleccionarSerializer(many=True),
    )
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenCiudad.objects.select_related('estado')
        search = request.query_params.get('search', '').strip()

        ciudad_id = self._entero(request, 'id')
        if ciudad_id is not None:
            qs = qs.filter(id=ciudad_id)

        estado_id = self._entero(request, 'estado')
        if estado_id is not None:
            qs = qs.filter(estado_id=estado_id)

        if search:
            qs = qs.filter(nombre__icontains=search)

        pagina = self.paginate_queryset(qs)
        serializer = GenCiudadSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @staticmethod
    def _entero(request, parametro):
        """
        El parámetro como entero, o `None` si no vino.

        Sin esta conversión un `?estado=abc` llega al ORM y sale como 500: Django
        levanta `ValueError` al armar la consulta, no un error de validación. Lo
        que corresponde es un 400 diciendo cuál parámetro está mal.
        """
        valor = request.query_params.get(parametro, '').strip()
        if not valor:
            return None
        try:
            return int(valor)
        except ValueError:
            raise ValidationError({parametro: 'Debe ser un número entero.'})
