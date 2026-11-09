from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from contabilidad.models import ConExogenaFormato
from contabilidad.serializers import ConExogenaFormatoSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por número o nombre del formato'),
]


@extend_schema(tags=['Exógena formato'])
class ConExogenaFormatoViewSet(viewsets.GenericViewSet):
    serializer_class = ConExogenaFormatoSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConExogenaFormatoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConExogenaFormato.objects.order_by('id')
        search = request.query_params.get('search', '').strip()
        if search:
            filtro = Q(nombre__icontains=search)
            if search.isdigit():
                filtro |= Q(id=int(search))
            qs = qs.filter(filtro)
        pagina = self.paginate_queryset(qs)
        serializer = ConExogenaFormatoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
