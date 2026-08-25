import logging

from django.conf import settings
from django.core import signing
from django.db import models
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from rest_framework.parsers import MultiPartParser

from seguridad import mfa as servicio_mfa
from seguridad.foto import subir_foto
from seguridad.models import METODO_SMS, SegMfaUsuario, SegUsuario
from seguridad.serializers import SegUsuarioActualizarSerializer, SegUsuarioMeSerializer, SegUsuarioSeleccionarSerializer, SegUsuarioSerializer
from utilidades.paginacion import SeleccionarPaginacion
from utilidades.turnstile import verify_turnstile
from utilidades.zinc import Zinc

logger = logging.getLogger(__name__)

_SALT_VERIFICACION = 'seg-verificacion-email'
_TIEMPO_VERIFICACION = 72 * 3600  # 72 horas

_SALT_RECUPERAR = 'seg-recuperar-clave'
_TIEMPO_RECUPERAR = 3600  # 1 hora

_RespuestaDetalle = inline_serializer(
    name='UsuarioDetailResponse',
    fields={'detail': serializers.CharField()},
)


class SegUsuarioViewSet(viewsets.ModelViewSet):
    queryset = SegUsuario.objects.all()
    serializer_class = SegUsuarioSerializer

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return SegUsuarioActualizarSerializer
        return SegUsuarioSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return super().get_permissions()

    def get_authenticators(self):
        if getattr(self, 'action', None) == 'create':
            return []
        return super().get_authenticators()

    def update(self, request, *args, **kwargs):
        rechazo = self._validar_cambio_de_celular(request)
        if rechazo is not None:
            return rechazo
        return super().update(request, *args, **kwargs)

    def _validar_cambio_de_celular(self, request):
        """
        Cambiar el celular con la verificación por SMS activa exige volver a probar el
        segundo factor.

        Sin esto, quien se apodere de una sesión abierta apunta los códigos a su propio
        número y se queda con la cuenta; y el titular podría dejarse a sí mismo sin
        recibir códigos con solo teclear mal el número.

        Devuelve la `Response` de rechazo, o None si el cambio puede seguir.
        """
        if 'celular' not in request.data:
            return None

        usuario = self.get_object()
        activo = SegMfaUsuario.objects.filter(
            usuario=usuario, activo=True, metodo=METODO_SMS,
        ).exists()
        if not activo:
            return None

        nuevo = servicio_mfa.normalizar_celular(request.data.get('celular'))
        if nuevo == servicio_mfa.normalizar_celular(usuario.celular):
            # Mismo número escrito distinto: no hay nada que proteger.
            return None

        if not nuevo:
            return Response(
                {'detail': 'Con la verificación por SMS activa, el celular debe ser un número válido de 10 dígitos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mfa_token = request.data.get('mfa_token')
        codigo = request.data.get('codigo')
        if not mfa_token or not codigo:
            # `codigo` le dice al front que abra el diálogo del segundo factor, igual
            # que `suscripcion_vencida` en SuscripcionVigente.
            return Response(
                {
                    'detail': 'Para cambiar tu celular confirma el código de verificación.',
                    'codigo': 'mfa_requerido',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            verificado = servicio_mfa.verificar_desafio(mfa_token, codigo).usuario
        except servicio_mfa.MfaError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if verificado != usuario:
            return Response(
                {'detail': 'La sesión de verificación expiró. Intenta de nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def get_throttles(self):
        scopes = {
            'create': 'registro',
            'recuperar_clave': 'recuperar_clave',
            'restablecer_clave': 'restablecer_clave',
        }
        if self.action in scopes:
            self.throttle_scope = scopes[self.action]
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        verify_turnstile(request.data.get('turnstile_token', ''), request.META.get('REMOTE_ADDR'))
        serializador = self.get_serializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        usuario = serializador.save()

        token = signing.dumps(usuario.email, salt=_SALT_VERIFICACION)
        verificacion_url = f'{settings.FRONTEND_URL}/auth/verify-email?token={token}'
        contenido_html = (
            f'<h1>¡Hola {usuario.nombre_corto}!</h1>'
            f'<p>Por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>'
            f'<a href="{verificacion_url}">Verificar cuenta</a>'
        )
        try:
            Zinc().correo(usuario.email, 'Verifica tu cuenta', contenido_html)
        except Exception as e:
            logger.warning('No se pudo enviar correo de verificación a %s: %s', usuario.email, e)

        cabeceras = self.get_success_headers(serializador.data)
        return Response(serializador.data, status=status.HTTP_201_CREATED, headers=cabeceras)

    @extend_schema(
        tags=['Autenticación'],
        summary='Verificar email',
        description='Activa la cuenta con el token del link enviado al correo. Válido 72 horas.',
        responses={
            200: _RespuestaDetalle,
            400: OpenApiResponse(_RespuestaDetalle, description='Token inválido o expirado'),
            404: OpenApiResponse(_RespuestaDetalle, description='Usuario no encontrado'),
        },
    )
    @action(detail=False, methods=['get'], url_path='verificar-email',
            permission_classes=[AllowAny], authentication_classes=[])
    def verificar_email(self, request):
        token = request.query_params.get('token', '').strip()
        if not token:
            return Response({'detail': 'Token requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            correo = signing.loads(token, salt=_SALT_VERIFICACION, max_age=_TIEMPO_VERIFICACION)
        except signing.SignatureExpired:
            return Response(
                {'detail': 'El enlace ha expirado. Solicita uno nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response({'detail': 'Token inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = SegUsuario.objects.get(email=correo)
        except SegUsuario.DoesNotExist:
            return Response({'detail': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if usuario.is_verified:
            return Response({'detail': 'La cuenta ya estaba verificada.'})

        usuario.is_verified = True
        usuario.save(update_fields=['is_verified'])
        return Response({'detail': 'Cuenta verificada. Ya puedes iniciar sesión.'})

    @extend_schema(
        tags=['Autenticación'],
        summary='Reenviar email de verificación',
        description='Reenvía el correo de verificación si la cuenta aún no está activa.',
        request=inline_serializer(
            name='ReenviarVerificacionRequest',
            fields={'email': serializers.EmailField()},
        ),
        responses={200: _RespuestaDetalle},
    )
    @action(detail=False, methods=['post'], url_path='reenviar-verificacion',
            permission_classes=[AllowAny], authentication_classes=[])
    def reenviar_verificacion(self, request):
        correo = request.data.get('email', '').strip().lower()
        if not correo:
            return Response({'detail': 'Email requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        _RESPUESTA_GENERICA = Response(
            {'detail': 'Si la cuenta existe, recibirás un correo de verificación.'}
        )

        try:
            usuario = SegUsuario.objects.get(email=correo)
        except SegUsuario.DoesNotExist:
            return _RESPUESTA_GENERICA

        if usuario.is_verified:
            return _RESPUESTA_GENERICA

        token = signing.dumps(usuario.email, salt=_SALT_VERIFICACION)
        verificacion_url = f'{settings.FRONTEND_URL}/auth/verify-email?token={token}'
        contenido_html = (
            f'<h1>¡Hola {usuario.nombre_corto}!</h1>'
            f'<p>Por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>'
            f'<a href="{verificacion_url}">Verificar cuenta</a>'
        )
        try:
            Zinc().correo(usuario.email, 'Verifica tu cuenta', contenido_html)
        except Exception as e:
            logger.warning('No se pudo enviar correo de verificación a %s: %s', usuario.email, e)

        return _RESPUESTA_GENERICA

    @extend_schema(exclude=True)
    @action(detail=False, methods=['post'], url_path='recuperar-clave',
            permission_classes=[AllowAny], authentication_classes=[])
    def recuperar_clave(self, request):
        verify_turnstile(request.data.get('turnstile_token', ''), request.META.get('REMOTE_ADDR'))
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'detail': 'Email requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = SegUsuario.objects.get(email=email)
        except SegUsuario.DoesNotExist:
            return Response(
                {'detail': 'No existe una cuenta registrada con este correo.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not usuario.is_verified:
            return Response(
                {'detail': 'La cuenta no está verificada. Revisa tu correo para activarla.', 'is_verified': False},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = signing.dumps(email, salt=_SALT_RECUPERAR)
        reset_link = f'{settings.FRONTEND_URL}/auth/restablecer-clave?token={token}'
        html_content = (
            f'<h1>Recuperación de clave</h1>'
            f'<p>Recibimos una solicitud para restablecer la clave de tu cuenta.</p>'
            f'<p>Haz clic en el siguiente enlace para crear una nueva clave:</p>'
            f'<a href="{reset_link}">Restablecer clave</a>'
            f'<p>Si no solicitaste esto, ignora este correo.</p>'
        )
        try:
            Zinc().correo(email, 'Recuperación de clave', html_content)
        except Exception as e:
            logger.warning('No se pudo enviar correo de recuperación a %s: %s', email, e)

        return Response({'detail': 'Se envía correo para recuperar la clave.'})

    @extend_schema(exclude=True)
    @action(detail=False, methods=['post'], url_path='restablecer-clave',
            permission_classes=[AllowAny], authentication_classes=[])
    def restablecer_clave(self, request):
        verify_turnstile(request.data.get('turnstile_token', ''), request.META.get('REMOTE_ADDR'))
        token = request.data.get('token', '').strip()
        nueva_clave = request.data.get('nueva_clave', '')

        if not token or not nueva_clave:
            return Response(
                {'detail': 'Token y nueva_clave son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(nueva_clave) < 8:
            return Response(
                {'detail': 'La clave debe tener al menos 8 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            email = signing.loads(token, salt=_SALT_RECUPERAR, max_age=_TIEMPO_RECUPERAR)
        except signing.SignatureExpired:
            return Response(
                {'detail': 'El enlace ha expirado. Solicita uno nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response({'detail': 'Token inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = SegUsuario.objects.get(email=email)
        except SegUsuario.DoesNotExist:
            return Response({'detail': 'Token inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        usuario.set_password(nueva_clave)
        usuario.save(update_fields=['password'])
        # No emite tokens a propósito: el usuario vuelve a /login/, y si tiene MFA activo
        # se le pide igual. Emitir sesión acá convertiría el "olvidé mi clave" —que se
        # resuelve por correo— en una forma de saltarse el segundo factor.
        return Response({'detail': 'Clave restablecida correctamente.'})

    @extend_schema(
        tags=['Usuarios'],
        summary='Subir foto de perfil',
        description='Acepta JPEG, PNG o WEBP (máx 5 MB). Genera original (1024px) y thumbnail (320×320) en WEBP.',
        request=inline_serializer(
            name='FotoRequest',
            fields={'foto': serializers.ImageField()},
        ),
        responses={200: SegUsuarioMeSerializer},
    )
    @action(detail=False, methods=['post'], url_path='foto', parser_classes=[MultiPartParser])
    def foto(self, request):
        archivo = request.FILES.get('foto')
        if not archivo:
            return Response({'detail': 'Campo foto requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Un fallo de B2 sale como ErrorDeAlmacenamiento (502) desde la capa
            # de backblaze; acá solo se traduce lo que es culpa del archivo.
            subir_foto(archivo, request.user)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SegUsuarioMeSerializer(request.user).data)

    @extend_schema(
        tags=['Usuarios'],
        summary='Seleccionar usuario',
        description='Retorna id, nombre_corto y email. Busca por nombre o email (paginado de a 50).',
        parameters=[
            OpenApiParameter('search', str, description='Buscar por nombre o email'),
        ],
        responses=SegUsuarioSeleccionarSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='seleccionar', pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        search = request.query_params.get('search', '').strip()
        # SegUsuario.Meta no define `ordering`, y paginar sin orden reparte los
        # mismos usuarios entre páginas distintas; `email` es único y desempata.
        qs = SegUsuario.objects.all().order_by('nombre_corto', 'email')
        if search:
            qs = qs.filter(
                models.Q(nombre_corto__icontains=search) | models.Q(email__icontains=search)
            )
        pagina = self.paginate_queryset(qs)
        serializer = SegUsuarioSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(exclude=True)
    @action(detail=False, methods=['post'], url_path='cambiar-clave')
    def cambiar_clave(self, request):
        usuario = request.user
        clave_actual = request.data.get('clave_actual', '')
        clave_nueva = request.data.get('clave_nueva', '')

        if not clave_actual or not clave_nueva:
            return Response(
                {'detail': 'clave_actual y nueva son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not usuario.check_password(clave_actual):
            return Response({'detail': 'La clave actual es incorrecta.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(clave_nueva) < 8:
            return Response(
                {'detail': 'La nueva clave debe tener al menos 8 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario.set_password(clave_nueva)
        usuario.save(update_fields=['password'])
        return Response({'detail': 'Clave actualizada correctamente.'})
