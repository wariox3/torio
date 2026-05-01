from django.db import transaction
from rest_framework import viewsets

from contenedor.models import CtnCliente, CtnDominio
from contenedor.serializers import CtnClienteSerializer


class CtnClienteViewSet(viewsets.ModelViewSet):
    queryset = CtnCliente.objects.all()
    serializer_class = CtnClienteSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        dominio = serializer.validated_data.pop('dominio')
        cliente = serializer.save(owner=self.request.user)
        CtnDominio.objects.create(domain=dominio, is_primary=True, tenant=cliente)
