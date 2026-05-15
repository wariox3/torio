from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnContacto
from contenedor.serializers import CtnContactoSerializer


@extend_schema(tags=['Contacto'])
class CtnContactoViewSet(viewsets.ModelViewSet):
    serializer_class = CtnContactoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CtnContacto.objects.select_related(
            'identificacion', 'ciudad', 'usuario'
        ).filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    @extend_schema(
        summary='Contactos del usuario autenticado',
        description='Retorna los contactos creados por el usuario autenticado.',
        responses=CtnContactoSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='lista-usuario')
    def lista_usuario(self, request):
        qs = CtnContacto.objects.filter(
            usuario=request.user,
        ).select_related('identificacion', 'ciudad', 'usuario')
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CtnContactoSerializer(pagina, many=True).data)
