from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnCliente, CtnDominio
from contenedor.serializers import CtnClienteSerializer
from contenedor.serializers.cliente import CtnClienteListaUsuarioSerializer
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

        schema_name = serializador.validated_data['schema_name']
        dominio = f'{schema_name}.{settings.TENANT_BASE_DOMAIN}'

        if CtnDominio.objects.filter(domain=dominio).exists():
            return Response(
                {'detail': f'El schema "{schema_name}" ya está registrado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cliente = serializador.save(owner=request.user)

        CtnDominio.objects.create(domain=dominio, is_primary=True, tenant=cliente)
        SegUsuarioTenant.objects.create(usuario=request.user, cliente=cliente)

        call_command('cargar_datos_tenant', schema=schema_name, verbosity=0)

        return Response(CtnClienteSerializer(cliente).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        try:
            cliente = self.get_object()
        except Exception:
            return Response(
                {'detail': f'El cliente con id "{kwargs.get("pk")}" no existe.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        cliente.delete(force_drop=True)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary='Listar contenedores del usuario',
        description='Retorna los clientes-tenant vinculados al usuario autenticado. Acepta `nombre` como query param para filtrar.',
        parameters=[
            inline_serializer('FiltroNombreSerializer', {'nombre': serializers.CharField(required=False)}),
        ],
        responses={200: CtnClienteListaUsuarioSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='lista-usuario')
    def lista_usuario(self, request):
        ids_cliente = SegUsuarioTenant.objects.filter(
            usuario=request.user
        ).values_list('cliente_id', flat=True)

        clientes = CtnCliente.objects.filter(id__in=ids_cliente, activo=True)

        nombre = request.query_params.get('nombre')
        if nombre:
            clientes = clientes.filter(nombre__icontains=nombre)

        pagina = self.paginate_queryset(clientes)
        serializador = CtnClienteListaUsuarioSerializer(pagina, many=True)
        return self.get_paginated_response(serializador.data)
