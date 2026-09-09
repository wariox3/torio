from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from general.models import GenDocumentoTipo
from general.serializers import (
    GenDocumentoTipoActualizarSerializer,
    GenDocumentoTipoSeleccionarSerializer,
    GenDocumentoTipoSerializer,
)
from utilidades.mixins import FiltrosDinamicosMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Documento tipo'])
class GenDocumentoTipoViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Catálogo normativo: los tipos los siembra `general/fixtures/11_documento_tipo.json`
    y no se crean ni se borran por la API. Lo único que cada tenant configura es su
    numeración y las cuentas de cartera, y eso es lo que acepta el PATCH.
    """

    serializer_class = GenDocumentoTipoSerializer

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return GenDocumentoTipoActualizarSerializer
        return GenDocumentoTipoSerializer

    def get_queryset(self):
        qs = GenDocumentoTipo.objects.select_related(
            *GenDocumentoTipoSerializer.select_related_lista
        )
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenDocumentoTipoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenDocumentoTipo.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenDocumentoTipoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
