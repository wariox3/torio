from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnPlan
from contenedor.serializers import CtnPlanListaSerializer, CtnPlanSerializer

_SEARCH_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre (retorna 10 resultados)'),
]


@extend_schema(tags=['Plan'])
class CtnPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        if self.action == 'list':
            return CtnPlanListaSerializer
        return CtnPlanSerializer

    @extend_schema(parameters=_SEARCH_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = CtnPlan.objects.all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        return qs
