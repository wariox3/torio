from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets

from general.models import GenPrecioDetalle
from general.serializers import GenPrecioDetalleImportarSerializer, GenPrecioDetalleSerializer
from utilidades.mixins import FiltrosDinamicosMixin, ImportarExcelMixin

_LIST_PARAMS = [
    OpenApiParameter('precio_id', int, description='Filtrar por precio'),
    OpenApiParameter('item_id', int, description='Filtrar por item'),
]


@extend_schema(tags=['PrecioDetalle'])
class GenPrecioDetalleViewSet(
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenPrecioDetalleSerializer
    serializer_class_importar = GenPrecioDetalleImportarSerializer

    def get_queryset(self):
        qs = GenPrecioDetalle.objects.select_related(
            *GenPrecioDetalleSerializer.select_related_lista
        ).order_by('-id')

        for filtro in ('precio_id', 'item_id'):
            valor = self.request.query_params.get(filtro)
            if valor:
                qs = qs.filter(**{filtro: valor})

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
