from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from contabilidad.models import ConCuentaGrupo
from contabilidad.serializers import ConCuentaGrupoSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Cuenta grupo'])
class ConCuentaGrupoViewSet(viewsets.GenericViewSet):
    serializer_class = ConCuentaGrupoSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConCuentaGrupoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConCuentaGrupo.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConCuentaGrupoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
