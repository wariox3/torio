from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnDatosFacturacion
from contenedor.serializers import CtnDatosFacturacionSerializer


@extend_schema(tags=['DatosFacturacion'])
class CtnDatosFacturacionViewSet(viewsets.ModelViewSet):
    serializer_class = CtnDatosFacturacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CtnDatosFacturacion.objects.select_related(
            'identificacion', 'ciudad', 'usuario'
        ).filter(usuario=self.request.user)
