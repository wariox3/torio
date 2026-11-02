from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from utilidades.carbono import TIPOS_CASO, Carbono

# Módulo «General» de carbono (`GET /api/soporte/modulo/lista`).
MODULO_GENERAL = 'GEN'
# Teléfono que se manda cuando el usuario no tiene celular en su perfil.
TELEFONO_SIN_CELULAR = '123456789'
# Carbono admite 5 adjuntos de 10 MB. El total se baja a 20 MB porque nginx corta
# en 21 MB (`client_max_body_size`, DESPLIEGUE.md §9) antes de llegar a Django.
MAXIMO_ADJUNTOS = 5
TAMANO_MAXIMO_ADJUNTO = 10 * 1024 * 1024
TAMANO_MAXIMO_ADJUNTOS = 20 * 1024 * 1024


class CasoNuevoSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TIPOS_CASO)
    # El mismo límite que tiene la columna en carbono.
    descripcion = serializers.CharField(max_length=5000)
    archivos = serializers.ListField(
        child=serializers.FileField(), required=False, max_length=MAXIMO_ADJUNTOS,
        error_messages={'max_length': f'Máximo {MAXIMO_ADJUNTOS} archivos por caso.'},
    )


_Detalle = inline_serializer('MesaAyudaDetalleSerializer', {'detail': serializers.CharField()})


@extend_schema(tags=['Mesa de ayuda'])
class CtnMesaAyudaViewSet(viewsets.ViewSet):
    """
    La mesa de ayuda carbono (`utilidades/carbono.py`), una acción por operación.

    Está en el schema público porque un caso es del usuario, no de un contenedor.
    Los datos de contacto salen siempre de `request.user`, nunca del body, para
    que nadie abra casos a nombre de otro.
    """

    permission_classes = [IsAuthenticated]
    # Lo lee `ScopedRateThrottle`, que solo usan las acciones que lo piden. Va en la
    # clase porque `@action` no acepta atributos que el ViewSet no tenga.
    throttle_scope = 'mesa_ayuda_caso'

    @extend_schema(
        summary='Crear caso',
        description=(
            'Crea un caso en la mesa de ayuda, en el módulo General, con el id, el nombre, '
            'el correo y el celular del usuario autenticado. Si no tiene celular en su '
            'perfil se manda 123456789.\n\n'
            'Sin adjuntos acepta JSON. Con adjuntos va en `multipart/form-data`, repitiendo '
            '`archivos` por cada uno: máximo 5, de 10 MB cada uno y 20 MB entre todos. '
            'El caso se crea aunque carbono no pueda guardar algún adjunto; '
            '`adjuntos_fallidos` dice cuántos.'
        ),
        request={
            'multipart/form-data': CasoNuevoSerializer,
            'application/json': CasoNuevoSerializer,
        },
        responses={
            201: inline_serializer('MesaAyudaCasoSerializer', {
                'id': serializers.IntegerField(),
                'adjuntos_fallidos': serializers.IntegerField(),
            }),
            400: OpenApiResponse(_Detalle, description='Datos inválidos o carbono rechazó el caso'),
            502: OpenApiResponse(_Detalle, description='La mesa de ayuda no respondió'),
        },
    )
    @action(
        detail=False, methods=['post'], url_path='caso',
        throttle_classes=[ScopedRateThrottle],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def caso(self, request):
        serializer = CasoNuevoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        archivos = datos.get('archivos', [])
        for archivo in archivos:
            if archivo.size > TAMANO_MAXIMO_ADJUNTO:
                raise serializers.ValidationError({
                    'detail': f'El archivo {archivo.name} supera los {TAMANO_MAXIMO_ADJUNTO // (1024 * 1024)} MB.',
                })
        if sum(archivo.size for archivo in archivos) > TAMANO_MAXIMO_ADJUNTOS:
            raise serializers.ValidationError({
                'detail': f'Los archivos suman más de {TAMANO_MAXIMO_ADJUNTOS // (1024 * 1024)} MB.',
            })

        usuario = request.user
        # Carbono exige teléfono, y el celular del perfil es opcional.
        telefono = (usuario.celular or '').strip() or TELEFONO_SIN_CELULAR

        # Carbono admite 200 caracteres en `contacto` y `cliente`; `nombre_corto`, 255.
        nombre = (usuario.nombre_corto or usuario.email)[:200]
        respuesta = Carbono().caso_nuevo(
            tipo=datos['tipo'],
            contacto=nombre,
            correo=usuario.email,
            telefono=telefono,
            descripcion=datos['descripcion'],
            # Los casos de torio no son de un contenedor ni de un módulo en
            # particular, pero carbono exige los dos.
            cliente=nombre,
            modulo=MODULO_GENERAL,
            usuario_integracion=usuario.id,
            # El archivo se pasa abierto, no leído: httpx lo va leyendo al enviar.
            archivos=[
                (archivo.name, archivo, archivo.content_type or 'application/octet-stream')
                for archivo in archivos
            ],
        )
        if not respuesta['error']:
            return Response(
                {
                    'id': respuesta['datos'].get('id'),
                    'adjuntos_fallidos': respuesta['datos'].get('adjuntosFallidos') or 0,
                },
                status=status.HTTP_201_CREATED,
            )
        # Un 400 de carbono es del caso (p. ej. la descripción) y su mensaje sirve al
        # usuario; cualquier otra cosa (token, caída, 5xx) es nuestra, y no se expone.
        if respuesta['status'] == 400:
            return Response(
                {'detail': respuesta['datos'].get('mensaje') or 'La mesa de ayuda rechazó el caso.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'detail': 'No fue posible crear el caso. Intenta de nuevo más tarde.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    @extend_schema(
        summary='Listar mis casos',
        description=(
            'Los 3 últimos casos que abrió el usuario autenticado, del más nuevo al más '
            'viejo. Carbono los busca por el id y el correo del usuario, así que los '
            'casos abiertos con un correo anterior no aparecen.'
        ),
        responses={
            200: inline_serializer('MesaAyudaCasoListaSerializer', {
                'id': serializers.IntegerField(),
                'descripcion': serializers.CharField(),
                'estado_atendido': serializers.BooleanField(),
                'estado_respuesta': serializers.BooleanField(),
                'estado_cerrado': serializers.BooleanField(),
            }, many=True),
            502: OpenApiResponse(_Detalle, description='La mesa de ayuda no respondió'),
        },
    )
    # Acción aparte y no GET sobre `caso/`: compartiría el throttle de crear y
    # consultar la lista gastaría el cupo de casos nuevos.
    @action(detail=False, methods=['get'], url_path='caso/lista')
    def caso_lista(self, request):
        usuario = request.user
        respuesta = Carbono().caso_lista_usuario_integracion(
            usuario_integracion=usuario.id, correo=usuario.email,
        )
        if respuesta['error']:
            # El id y el correo salen de la sesión, así que un 400 de carbono
            # tampoco es culpa del usuario.
            return Response(
                {'detail': 'No fue posible consultar los casos. Intenta de nuevo más tarde.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        casos = [
            {
                'id': caso.get('id'),
                'descripcion': caso.get('descripcion'),
                'estado_atendido': caso.get('estadoAtendido'),
                'estado_respuesta': caso.get('estadoRespuesta'),
                'estado_cerrado': caso.get('estadoCerrado'),
            }
            for caso in respuesta['datos'].get('casos') or []
        ]
        return Response(casos)
