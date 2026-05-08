from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnCliente, CtnDominio
from contenedor.serializers import CtnClienteSerializer
from seguridad.models import SegUsuarioTenant


@extend_schema(tags=['Cliente'])
class CtnClienteViewSet(viewsets.ModelViewSet):
    serializer_class = CtnClienteSerializer
    permission_classes = [IsAuthenticated]
    queryset = CtnCliente.objects.all()

    @extend_schema(
        summary='Crear tenant',
        description='Crea un nuevo cliente tenant con su schema PostgreSQL, dominio y vincula al usuario autenticado como owner.',
        responses={
            201: CtnClienteSerializer,
            400: OpenApiResponse(
                inline_serializer('ErrorSerializer', {'detail': serializers.CharField()}),
                description='Dominio o schema ya registrado',
            ),
        },
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializador = CtnClienteSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        dominio = serializador.validated_data.pop('dominio')

        if CtnDominio.objects.filter(domain=dominio).exists():
            return Response(
                {'detail': f'El dominio "{dominio}" ya está registrado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cliente = serializador.save(owner=request.user)

        CtnDominio.objects.create(domain=dominio, is_primary=True, tenant=cliente)
        SegUsuarioTenant.objects.create(usuario=request.user, cliente=cliente)

        return Response(CtnClienteSerializer(cliente).data, status=status.HTTP_201_CREATED)
