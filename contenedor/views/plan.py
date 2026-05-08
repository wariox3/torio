from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnPlan
from contenedor.serializers import CtnPlanSeleccionarSerializer, CtnPlanSerializer

_SELECCIONAR_PARAMS = [
    OpenApiParameter('plan_tipo_id', str, description='Filtrar por tipo de plan (F, E, P)'),
    OpenApiParameter('search', str, description='Buscar por nombre (retorna 10 resultados)'),
]


_LIST_PARAMS = [
    OpenApiParameter('plan_tipo_id', str, description='Filtrar por tipo de plan (F, E, P)'),
]


@extend_schema(tags=['Plan'])
class CtnPlanViewSet(viewsets.ModelViewSet):
    serializer_class = CtnPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnPlan.objects.all()
        plan_tipo_id = self.request.query_params.get('plan_tipo_id')
        if plan_tipo_id:
            qs = qs.filter(plan_tipo_id=plan_tipo_id)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=CtnPlanSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'])
    def seleccionar(self, request):
        qs = CtnPlan.objects.all()
        plan_tipo_id = request.query_params.get('plan_tipo_id')
        search = request.query_params.get('search', '').strip()
        if plan_tipo_id:
            qs = qs.filter(plan_tipo_id=plan_tipo_id)
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        serializer = CtnPlanSeleccionarSerializer(qs, many=True)
        return Response(serializer.data)
