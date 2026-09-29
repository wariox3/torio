from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models import Prefetch
from django.utils import timezone
from django_tenants.utils import schema_exists
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo
from contenedor.serializers import CtnClienteSerializer
from contenedor.serializers.cliente import (
    CtnClienteActualizarSerializer,
    CtnClienteListaUsuarioSerializer,
)
from contenedor.tasks import clave_paso, programar_creacion
from seguridad.models import CAMPOS_ACCESO, SegUsuario, SegUsuarioCliente

# Todo contenedor nuevo arranca en el mismo plan de prueba —'Prueba ERP', categoría
# 99, precio 0— por quince días. No es algo que elija quien crea el tenant: para
# cambiar de plan está `/contenedor/suscripcion/`.
SUSCRIPCION_TIPO_PRUEBA_ID = 13
DIAS_PRUEBA = 15

# Un contenedor tarda unos 20 s en crearse. Si sigue en `creando` pasado este
# tiempo, la tarea se perdió —un mensaje que RabbitMQ no entregó, un worker muerto
# por el límite duro— y `reintentar` lo deja volver a encolar.
CREACION_ATASCADA = timedelta(minutes=30)


@extend_schema(tags=['Cliente'])
class CtnClienteViewSet(viewsets.ModelViewSet):
    serializer_class = CtnClienteSerializer
    permission_classes = [IsAuthenticated]
    queryset = CtnCliente.objects.all()

    # Alcance del `ScopedRateThrottle` que `get_throttles` le suma a `create`.
    throttle_scope = 'crear_contenedor'

    def get_queryset(self):
        # Un usuario solo ve y opera sobre los contenedores de los que es
        # miembro. `create` no usa el queryset, así que no queda bloqueado.
        # La autorización fina de escritura (update/destroy) la refina cada
        # acción contra is_superuser del contenedor.
        #
        # Un contenedor en `creando` ya aparece: la membresía del owner la crea
        # el request, no la tarea.
        return CtnCliente.objects.filter(
            segusuariocliente__usuario=self.request.user,
        ).distinct()

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return CtnClienteActualizarSerializer
        return CtnClienteSerializer

    def get_throttles(self):
        # Solo `create` lleva el límite propio; el resto de acciones, solo los
        # límites generales.
        throttles = super().get_throttles()
        if self.action == 'create':
            throttles.append(ScopedRateThrottle())
        return throttles

    @extend_schema(
        summary='Crear tenant',
        description=(
            'Registra el contenedor en `estado: creando` y responde 202 enseguida: el '
            'schema, las migraciones y los catálogos los termina una tarea en segundo '
            'plano. El front consulta `GET /contenedor/cliente/<id>/estado/` hasta que '
            'llegue a `listo` (o a `error`, que se reintenta con '
            '`POST /contenedor/cliente/<id>/reintentar/`). Mientras no esté listo, '
            'cualquier request con su `X-Tenant` responde 409.'
        ),
        responses={
            202: CtnClienteSerializer,
            400: OpenApiResponse(
                inline_serializer('ErrorSerializer', {'detail': serializers.CharField()}),
                description='Nombre de schema inválido o ya registrado',
            ),
            409: OpenApiResponse(
                inline_serializer('ClienteEnCreacionSerializer', {'detail': serializers.CharField()}),
                description='El usuario ya tiene un contenedor en creación',
            ),
        },
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        La parte rápida de crear un contenedor: todo lo que vive en el schema
        público. Dura milisegundos; lo lento lo hace `contenedor.tasks.crear_contenedor`.

        Antes esto corría las 126 migraciones del tenant dentro de esta misma
        transacción, y las FKs hacia `seg_usuario` dejaban esa tabla bloqueada para
        escritura 10 s: nadie podía iniciar sesión mientras alguien creaba un
        contenedor. El porqué completo, en `docs/creacion_contenedor.md`.
        """
        serializador = CtnClienteSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        schema_name = serializador.validated_data['schema_name']
        dominio = f'{schema_name}.{settings.TENANT_BASE_DOMAIN}'

        # Va interpolado en `CREATE SCHEMA` (ver `CtnCliente.SCHEMA_NAME_VALIDO`).
        if not CtnCliente.SCHEMA_NAME_VALIDO.match(schema_name):
            return Response(
                {'detail': (
                    f'"{schema_name}" no es un nombre de schema válido: solo letras '
                    'minúsculas, números y guion bajo, empezando por una letra y sin '
                    'el prefijo "pg_".'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # `schema_exists` cubre un schema huérfano, que quedó sin su CtnCliente:
        # reutilizarlo metería al contenedor nuevo los datos de otro.
        if CtnDominio.objects.filter(domain=dominio).exists() or schema_exists(schema_name):
            return Response(
                {'detail': f'El schema "{schema_name}" ya está registrado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Se busca antes de crear nada: el FK admite null, así que sin esta guarda
        # el contenedor quedaría con una suscripción sin tipo y precio 0 en vez de
        # fallar. El catálogo lo carga `cargar_geodata` en el schema público.
        suscripcion_tipo = CtnSuscripcionTipo.objects.filter(pk=SUSCRIPCION_TIPO_PRUEBA_ID).first()
        if suscripcion_tipo is None:
            return Response(
                {'detail': f'Falta el tipo de suscripción de prueba (id={SUSCRIPCION_TIPO_PRUEBA_ID}).'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Uno en creación por usuario. Se cuenta en la base y no en el throttle
        # porque este sí tiene que valer con Redis caído. El lock sobre la fila del
        # usuario pone en fila dos POST suyos simultáneos: sin él, los dos verían
        # cero contenedores en creación y pasarían.
        SegUsuario.objects.select_for_update().filter(pk=request.user.pk).first()
        if CtnCliente.objects.filter(owner=request.user, estado=CtnCliente.ESTADO_CREANDO).exists():
            return Response(
                {'detail': 'Ya tienes un contenedor en creación. Espera a que termine.'},
                status=status.HTTP_409_CONFLICT,
            )

        cliente = CtnCliente(
            **serializador.validated_data,
            owner=request.user,
            estado=CtnCliente.ESTADO_CREANDO,
        )
        # En la instancia y no en la clase: `TenantTestCase`, el shell y el admin
        # siguen creando el schema al guardar.
        cliente.auto_create_schema = False
        try:
            # Savepoint propio: si el INSERT choca, la transacción de afuera sigue
            # usable para responder.
            with transaction.atomic():
                cliente.save()
        except IntegrityError:
            # Dos POST con el mismo nombre a la vez: los dos pasaron la validación
            # del serializer, y el índice único frena al segundo.
            return Response(
                {'detail': f'El schema "{schema_name}" ya está registrado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # El schema vacío va acá y no en la tarea: `migrate_schemas` de cada deploy
        # recorre todos los CtnCliente y se cae con uno que no tenga schema —por
        # ejemplo, uno que quedó en `error` porque RabbitMQ no respondió—.
        # `CREATE SCHEMA` no toca ninguna tabla, así que no bloquea nada.
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{schema_name}"')

        CtnDominio.objects.create(domain=dominio, is_primary=True, tenant=cliente)

        # La membresía sí va acá, aunque sus permisos (`UserTenantPermissions`)
        # los crea la tarea: estos viven en el schema del tenant, que todavía no
        # tiene tablas. Así el contenedor aparece en `lista-usuario` desde ya.
        # El owner no necesita grupos —la tarea le da is_superuser, que se salta
        # TienePermisoModelo—, pero sí los accesos: por defecto son todos False y
        # se quedaría sin ningún módulo en el menú de su propio contenedor.
        SegUsuarioCliente.objects.create(
            usuario=request.user,
            cliente=cliente,
            propietario=True,
            **dict.fromkeys(CAMPOS_ACCESO, True),
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

        programar_creacion(cliente.pk)

        return Response(CtnClienteSerializer(cliente).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        summary='Estado de creación del contenedor',
        description=(
            'Para consultar mientras el contenedor se crea. `paso` dice en qué va '
            '(`esquema`, `migraciones`, `permisos`, `catalogos`) y solo viene en '
            '`creando`; puede faltar aunque esté creando, porque se guarda en caché.'
        ),
        responses={200: inline_serializer('ClienteEstadoSerializer', {
            'estado': serializers.ChoiceField(choices=CtnCliente.ESTADO_CHOICES),
            'paso': serializers.CharField(allow_null=True),
        })},
    )
    @action(detail=True, methods=['get'], url_path='estado')
    def estado(self, request, pk=None):
        cliente = self.get_object()
        paso = None
        if cliente.estado == CtnCliente.ESTADO_CREANDO:
            paso = cache.get(clave_paso(cliente.pk))
        return Response({'estado': cliente.estado, 'paso': paso})

    @extend_schema(
        summary='Reintentar la creación del contenedor',
        description=(
            'Vuelve a encolar la creación de un contenedor en `error`, o en `creando` '
            'hace más de 30 minutos (la tarea se perdió). Retoma donde quedó: lo ya '
            'migrado o cargado no se repite. Solo el owner.'
        ),
        request=None,
        responses={
            202: CtnClienteSerializer,
            403: OpenApiResponse(
                inline_serializer('ClienteReintentarForbiddenSerializer', {'detail': serializers.CharField()}),
                description='No es el owner',
            ),
            409: OpenApiResponse(
                inline_serializer('ClienteReintentarConflictoSerializer', {'detail': serializers.CharField()}),
                description='El contenedor está listo o se sigue creando',
            ),
        },
    )
    @action(detail=True, methods=['post'], url_path='reintentar')
    @transaction.atomic
    def reintentar(self, request, pk=None):
        # El filtro de `get_queryset` sin su `distinct`, que PostgreSQL no admite
        # con FOR UPDATE. El lock pone en fila dos reintentos simultáneos.
        cliente = CtnCliente.objects.select_for_update(of=('self',)).filter(
            pk=pk, segusuariocliente__usuario=request.user,
        ).first()
        if cliente is None:
            return Response(
                {'detail': f'El cliente con id "{pk}" no existe.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Por owner y no por `es_superusuario`: esa consulta lee el schema del
        # tenant, que en un contenedor fallido puede no tener tablas.
        if cliente.owner_id != request.user.id:
            return Response(
                {'detail': 'Solo el owner del contenedor puede reintentar su creación.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        atascado = (
            cliente.estado == CtnCliente.ESTADO_CREANDO
            and cliente.fecha_creacion is not None
            and cliente.fecha_creacion < timezone.now() - CREACION_ATASCADA
        )
        if cliente.estado != CtnCliente.ESTADO_ERROR and not atascado:
            detalle = (
                'El contenedor ya está listo.'
                if cliente.estado == CtnCliente.ESTADO_LISTO
                else 'El contenedor se está creando.'
            )
            return Response({'detail': detalle}, status=status.HTTP_409_CONFLICT)

        # Reintentar uno atascado dos veces seguidas encola dos tareas, y no pasa
        # nada: si coinciden, el candado de la tarea deja pasar solo a una, y si no,
        # la segunda lo encuentra `listo` y no hace nada.
        # `update` y no `save`: el `save` de django-tenants crea el schema en ese
        # mismo llamado si no lo encuentra, y eso es justo lo que no va en el request.
        CtnCliente.objects.filter(pk=cliente.pk).update(estado=CtnCliente.ESTADO_CREANDO)
        cliente.estado = CtnCliente.ESTADO_CREANDO
        programar_creacion(cliente.pk)

        return Response(CtnClienteSerializer(cliente).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        summary='Actualizar contenedor',
        responses={
            200: CtnClienteActualizarSerializer,
            403: OpenApiResponse(
                inline_serializer('ClienteForbiddenSerializer', {'detail': serializers.CharField()}),
                description='Sin permisos de superusuario en el contenedor',
            ),
            409: OpenApiResponse(
                inline_serializer('ClienteNoListoSerializer', {'detail': serializers.CharField()}),
                description='El contenedor no está listo',
            ),
        },
    )
    def update(self, request, *args, **kwargs):
        cliente = self.get_object()
        # `es_superusuario` lee el schema del tenant, que mientras se crea no
        # tiene tablas.
        if cliente.estado != CtnCliente.ESTADO_LISTO:
            return Response(
                {'detail': 'El contenedor todavía no está listo.'},
                status=status.HTTP_409_CONFLICT,
            )
        if not cliente.es_superusuario(request.user):
            return Response(
                {'detail': 'Solo un superusuario del contenedor puede modificarlo.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary='Eliminar contenedor',
        description=(
            'Elimina el cliente y su schema. Solo un superusuario del contenedor puede '
            'hacerlo; si la creación falló (`estado: error`), el owner. Uno en '
            '`creando` no se puede eliminar hasta que termine.'
        ),
        responses={
            204: None,
            403: OpenApiResponse(
                inline_serializer('ClienteDeleteForbiddenSerializer', {'detail': serializers.CharField()}),
                description='Sin permisos de superusuario en el contenedor',
            ),
            409: OpenApiResponse(
                inline_serializer('ClienteDeleteCreandoSerializer', {'detail': serializers.CharField()}),
                description='El contenedor se está creando',
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

        # Borrarlo mientras la tarea corre sería tirarle el schema debajo.
        if cliente.estado == CtnCliente.ESTADO_CREANDO:
            return Response(
                {'detail': 'El contenedor se está creando. Espera a que termine.'},
                status=status.HTTP_409_CONFLICT,
            )

        # La autorización se resuelve contra permissions_usertenantpermissions
        # del schema del contenedor (is_superuser), no contra owner_id: esa es
        # la fuente de verdad de permisos y es la que puebla add_user al crear.
        # Salvo en uno fallido, donde ese schema puede no tener tablas: ahí,
        # por owner.
        if cliente.estado == CtnCliente.ESTADO_ERROR:
            autorizado = cliente.owner_id == request.user.id
        else:
            autorizado = cliente.es_superusuario(request.user)
        if not autorizado:
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
