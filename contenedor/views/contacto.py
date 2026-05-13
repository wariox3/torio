from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
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
