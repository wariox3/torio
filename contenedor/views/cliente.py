from datetime import date, timedelta

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Prefetch

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo
from contenedor.serializers import CtnClienteSerializer
from contenedor.serializers.cliente import CtnClienteActualizarSerializer, CtnClienteListaUsuarioSerializer
from seguridad.models import CAMPOS_ACCESO, SegUsuarioCliente

# Todo contenedor nuevo arranca en el mismo plan de prueba —'Prueba ERP', categoría
# 99, precio 0— por quince días. No es algo que elija quien crea el tenant: para
# cambiar de plan está `/contenedor/suscripcion/`.
SUSCRIPCION_TIPO_PRUEBA_ID = 13
DIAS_PRUEBA = 15


@extend_schema(tags=['Cliente'])
class CtnClienteViewSet(viewsets.ModelViewSet):
    serializer_class = CtnClienteSerializer
    permission_classes = [IsAuthenticated]
    queryset = CtnCliente.objects.all()

    def get_queryset(self):
        # Un usuario solo ve y opera sobre los contenedores de los que es
        # miembro. `create` no usa el queryset, así que no queda bloqueado.
        # La autorización fina de escritura (update/destroy) la refina cada
        # acción contra is_superuser del contenedor.
        return CtnCliente.objects.filter(
            segusuariocliente__usuario=self.request.user,
        ).distinct()

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

        # Se busca antes de crear nada: el FK admite null, así que sin esta guarda
        # el contenedor quedaría con una suscripción sin tipo y precio 0 en vez de
        # fallar. El catálogo lo carga `cargar_geodata` en el schema público.
        suscripcion_tipo = CtnSuscripcionTipo.objects.filter(
            pk=SUSCRIPCION_TIPO_PRUEBA_ID,
        ).first()
        if suscripcion_tipo is None:
            return Response(
                {'detail': f'Falta el tipo de suscripción de prueba (id={SUSCRIPCION_TIPO_PRUEBA_ID}).'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        cliente = serializador.save(owner=request.user)

        CtnDominio.objects.create(domain=dominio, is_primary=True, tenant=cliente)
        # add_user crea la membresía y, dentro del schema recién creado, los
        # permisos del usuario. El owner no necesita grupos: is_superuser le
        # basta para saltarse TienePermisoModelo, y aplica solo a este
        # contenedor porque vive en su UserTenantPermissions, no en el usuario.
        # Los accesos sí hay que pasarlos: por defecto son todos False y el owner
        # se quedaría sin ningún módulo en el menú de su propio contenedor.
        cliente.add_user(
            request.user,
            accesos=dict.fromkeys(CAMPOS_ACCESO, True),
            propietario=True,
            is_superuser=True,
        )

        fecha_inicio = date.today()
        suscripcion = CtnSuscripcion.objects.create(
            cliente=cliente,
            usuario=request.user,
            suscripcion_tipo=suscripcion_tipo,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_inicio + timedelta(days=DIAS_PRUEBA),
            frecuencia=CtnSuscripcion.FRECUENCIA_PRUEBA,
        )
        cliente.suscripcion = suscripcion
        cliente.save(update_fields=['suscripcion'])

        call_command('cargar_datos_tenant', schema=schema_name, inicial=True, verbosity=0)

        return Response(CtnClienteSerializer(cliente).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Actualizar contenedor',
        responses={
            200: CtnClienteActualizarSerializer,
            403: OpenApiResponse(
                inline_serializer('ClienteForbiddenSerializer', {'detail': serializers.CharField()}),
                description='Sin permisos de superusuario en el contenedor',
            ),
        },
    )
    def update(self, request, *args, **kwargs):
        cliente = self.get_object()
        if not cliente.es_superusuario(request.user):
            return Response(
                {'detail': 'Solo un superusuario del contenedor puede modificarlo.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary='Eliminar contenedor',
        description='Elimina el cliente y su schema. Solo un superusuario del contenedor puede hacerlo.',
        responses={
            204: None,
            403: OpenApiResponse(
                inline_serializer('ClienteDeleteForbiddenSerializer', {'detail': serializers.CharField()}),
                description='Sin permisos de superusuario en el contenedor',
            ),
        },
    )
    def destroy(self, request, *args, **kwargs):
        try:
            cliente = self.get_object()
        except Exception:
            return Response(
                {'detail': f'El cliente con id "{kwargs.get("pk")}" no existe.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # La autorización se resuelve contra permissions_usertenantpermissions
        # del schema del contenedor (is_superuser), no contra owner_id: esa es
        # la fuente de verdad de permisos y es la que puebla add_user al crear.
        if not cliente.es_superusuario(request.user):
            return Response(
                {'detail': 'Solo un superusuario del contenedor puede eliminarlo.'},
                status=status.HTTP_403_FORBIDDEN,
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
        membresias = SegUsuarioCliente.objects.filter(
            usuario=request.user,
            cliente__activo=True,
        ).select_related(
            'cliente__suscripcion__suscripcion_tipo',
        ).prefetch_related(
            Prefetch(
                'cliente__domains',
                queryset=CtnDominio.objects.filter(is_primary=True),
                to_attr='_dominio_primario',
            )
        ).order_by('cliente__nombre')

        nombre = request.query_params.get('nombre')
        if nombre:
            membresias = membresias.filter(cliente__nombre__icontains=nombre)

        pagina = self.paginate_queryset(membresias)
        return self.get_paginated_response(CtnClienteListaUsuarioSerializer(pagina, many=True).data)
