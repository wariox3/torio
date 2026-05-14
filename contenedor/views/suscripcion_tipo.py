from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnSuscripcionTipo
from contenedor.serializers import CtnSuscripcionTipoSerializer

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
    OpenApiParameter('suscripcion_clase_id', int, description='Filtrar por clase de suscripción'),
    OpenApiParameter('suscripcion_categoria_id', int, description='Filtrar por categoría de suscripción'),
]


@extend_schema(tags=['SuscripcionTipo'])
class CtnSuscripcionTipoViewSet(viewsets.ModelViewSet):
    serializer_class = CtnSuscripcionTipoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnSuscripcionTipo.objects.order_by('id')
        search = self.request.query_params.get('search', '').strip()
        suscripcion_clase_id = self.request.query_params.get('suscripcion_clase_id')
        suscripcion_categoria_id = self.request.query_params.get('suscripcion_categoria_id')
        if search:
            qs = qs.filter(nombre__icontains=search)
        if suscripcion_clase_id:
            qs = qs.filter(suscripcion_clase_id=suscripcion_clase_id)
        if suscripcion_categoria_id:
            qs = qs.filter(suscripcion_categoria_id=suscripcion_categoria_id)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Listar tipos de suscripción por clase',
        parameters=[
            OpenApiParameter('clase_id', int, required=True, description='ID de la clase de suscripción'),
        ],
        responses={
            200: CtnSuscripcionTipoSerializer(many=True),
            400: OpenApiResponse(
                inline_serializer('ClaseIdRequerido', {'detail': serializers.CharField()}),
                description='clase_id requerido',
            ),
        },
    )
    @action(detail=False, methods=['get'], url_path='lista-clase')
    def lista_clase(self, request):
        clase_id = request.query_params.get('clase_id')
        if not clase_id:
            return Response({'detail': 'clase_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = CtnSuscripcionTipo.objects.filter(
            suscripcion_clase_id=clase_id,
        ).exclude(suscripcion_categoria_id=99).order_by('id')
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CtnSuscripcionTipoSerializer(pagina, many=True).data)
