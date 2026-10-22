from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from contabilidad.models import ConCuentaCuenta
from contabilidad.serializers import ConCuentaCuentaSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
    OpenApiParameter('id__gte', int, description='ID mayor o igual a'),
    OpenApiParameter('id__lte', int, description='ID menor o igual a'),
]


@extend_schema(tags=['Cuenta cuenta'])
class ConCuentaCuentaViewSet(viewsets.GenericViewSet):
    serializer_class = ConCuentaCuentaSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConCuentaCuentaSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConCuentaCuenta.objects.all()
        for filtro in ('id__gte', 'id__lte'):
            valor = request.query_params.get(filtro, '').strip()
            if valor:
                if not valor.isdigit():
                    raise ValidationError({'detail': f'El filtro "{filtro}" debe ser un número entero.'})
                qs = qs.filter(**{filtro: int(valor)})
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConCuentaCuentaSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
