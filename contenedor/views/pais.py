from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnPais
from contenedor.serializers import CtnPaisSerializer

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre (retorna 10 resultados)'),
]


@extend_schema(tags=['Pais'])
class CtnPaisViewSet(viewsets.ModelViewSet):
    serializer_class = CtnPaisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnPais.objects.all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=CtnPaisSerializer(many=True))
    @action(detail=False, methods=['get'])
    def seleccionar(self, request):
        qs = CtnPais.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        serializer = CtnPaisSerializer(qs, many=True)
        return Response(serializer.data)
