from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Prefetch

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion
from contenedor.serializers import CtnClienteSerializer
from contenedor.serializers.cliente import CtnClienteActualizarSerializer, CtnClienteListaUsuarioSerializer
from seguridad.models import SegRol, SegUsuarioCliente


@extend_schema(tags=['Cliente'])
class CtnClienteViewSet(viewsets.ModelViewSet):
    serializer_class = CtnClienteSerializer
    permission_classes = [IsAuthenticated]
    queryset = CtnCliente.objects.all()

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return CtnClienteActualizarSerializer
        return CtnClienteSerializer

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

        suscripcion_tipo = serializador.validated_data.pop('suscripcion_tipo')
        frecuencia = serializador.validated_data.pop('frecuencia')
        cliente = serializador.save(owner=request.user)

        CtnDominio.objects.create(domain=dominio, is_primary=True, tenant=cliente)
        rol_owner = SegRol.objects.filter(codigo='owner').first()
        SegUsuarioCliente.objects.create(usuario=request.user, cliente=cliente, rol=rol_owner)

        fecha_inicio = date.today()
        if frecuencia == CtnSuscripcion.FRECUENCIA_PRUEBA:
            fecha_fin = fecha_inicio + timedelta(days=15)
        elif frecuencia == CtnSuscripcion.FRECUENCIA_ANUAL:
            fecha_fin = fecha_inicio + relativedelta(years=1)
        else:
            fecha_fin = fecha_inicio + relativedelta(months=1)
        suscripcion = CtnSuscripcion.objects.create(
            cliente=cliente,
            usuario=request.user,
            suscripcion_tipo=suscripcion_tipo,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            frecuencia=frecuencia,
        )
        cliente.suscripcion = suscripcion
        cliente.save(update_fields=['suscripcion'])

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
        ids_cliente = SegUsuarioCliente.objects.filter(
            usuario=request.user
        ).values_list('cliente_id', flat=True)

        clientes = CtnCliente.objects.select_related(
            'suscripcion__suscripcion_tipo'
        ).prefetch_related(
            Prefetch(
                'domains',
                queryset=CtnDominio.objects.filter(is_primary=True),
                to_attr='_dominio_primario',
            )
        ).filter(id__in=ids_cliente, activo=True)

        nombre = request.query_params.get('nombre')
        if nombre:
            clientes = clientes.filter(nombre__icontains=nombre)

        pagina = self.paginate_queryset(clientes)
        serializador = CtnClienteListaUsuarioSerializer(pagina, many=True)
        return self.get_paginated_response(serializador.data)
