import logging

from django.conf import settings
from django.core import signing
from django.db import models
from django.db.models import ProtectedError
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from seguridad import cuenta as servicio_cuenta
from seguridad import mfa as servicio_mfa
from seguridad.foto import subir_foto
from seguridad.models import METODO_SMS, SegMfaUsuario, SegUsuario, SegUsuarioCliente
from seguridad.serializers import (
    SegUsuarioActualizarSerializer,
    SegUsuarioMeSerializer,
    SegUsuarioSeleccionarSerializer,
    SegUsuarioSerializer,
)
from utilidades.paginacion import SeleccionarPaginacion
from utilidades.telefono import a_nacional, normalizar_e164
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

    def get_queryset(self):
        # El CRUD es solo de la propia cuenta: sin este corte, cualquier sesión
        # listaba a todos los usuarios (correo, celular, identificación) y podía
        # editar o borrar cuentas ajenas. Una ajena responde 404, no 403, para no
        # confirmar que el id existe. Buscar a quién invitar es `seleccionar`.
        if self.action in ('list', 'retrieve', 'update', 'partial_update', 'destroy'):
            return SegUsuario.objects.filter(pk=self.request.user.pk).order_by('id')
        return super().get_queryset()

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

        nuevo = normalizar_e164(request.data.get('celular'))
        if nuevo == normalizar_e164(usuario.celular):
            # Mismo número escrito distinto: no hay nada que proteger.
            return None

        if not nuevo or not a_nacional(nuevo):
            # Con SMS activo el número es parte del segundo factor, así que además de
            # ser válido tiene que poder recibirlo: Zinc solo entrega en Colombia y
            # mudarse a un número extranjero dejaría la cuenta sin cómo verificarse.
            return Response(
                {
                    'detail': 'Con la verificación por SMS activa, el celular debe ser un '
                              'número colombiano válido que pueda recibir los códigos.',
                },
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

    @extend_schema(
        tags=['Usuarios'],
        summary='Eliminar la propia cuenta',
        description=(
            'Borra la cuenta por completo: la saca de todos los contenedores donde es '
            'miembro, cierra sus sesiones y borra su segundo factor, sus invitaciones y su '
            'foto. La bitácora de accesos, las solicitudes, los pagos y los contactos de '
            'facturación se conservan sin autor. Solo '
            'sobre la propia cuenta: otro id responde 404.\n\n'
            'Exige `password`. Con la verificación en dos pasos activa exige además '
            '`mfa_token` (de `POST /seguridad/mfa/desafio/`) y `codigo`; sin ellos responde '
            '400 con `codigo: mfa_requerido`.\n\n'
            'Responde 409 si la cuenta tiene una membresía como propietaria de algún '
            'contenedor: hay que eliminarlo primero, nunca se borra en cascada.'
        ),
        request=inline_serializer(
            name='UsuarioEliminarRequest',
            fields={
                'password': serializers.CharField(),
                'mfa_token': serializers.CharField(required=False),
                'codigo': serializers.CharField(required=False),
            },
        ),
        responses={
            204: None,
            400: OpenApiResponse(_RespuestaDetalle, description='Clave o código inválidos'),
            404: OpenApiResponse(_RespuestaDetalle, description='No es la propia cuenta'),
            409: OpenApiResponse(_RespuestaDetalle, description='Es propietaria de algún contenedor'),
        },
    )
    def destroy(self, request, *args, **kwargs):
        # El `destroy` de DRF llama a `usuario.delete()`, que django-tenant-users
        # prohíbe (DeleteError → 500), y su `delete_user()` a un propietario le
        # elimina los contenedores sin preguntar. El borrado está en `seguridad.cuenta`.
        usuario = self.get_object()

        password = request.data.get('password', '')
        if not password:
            return Response({'detail': 'password es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        if not usuario.check_password(password):
            return Response({'detail': 'La clave es incorrecta.'}, status=status.HTTP_400_BAD_REQUEST)

        # Antes del segundo factor, para no gastarle un código a quien igual va a
        # recibir un 409. Los contenedores no se borran en cascada: primero el
        # propietario los elimina. Cuenta la membresía (`propietario`), no
        # `CtnCliente.owner`, que es informativo y nulable.
        nombres = list(
            SegUsuarioCliente.objects.filter(usuario=usuario, propietario=True)
            .order_by('cliente__nombre')
            .values_list('cliente__nombre', flat=True)
        )
        if nombres:
            return Response(
                {
                    'detail': 'Eres propietario de: ' + ', '.join(nombres) + '. '
                              'Elimina primero esos contenedores para poder eliminar tu cuenta.',
                },
                status=status.HTTP_409_CONFLICT,
            )

        if servicio_mfa.mfa_activo(usuario):
            mfa_token = request.data.get('mfa_token')
            codigo = request.data.get('codigo')
            if not mfa_token or not codigo:
                return Response(
                    {
                        'detail': 'Para eliminar tu cuenta confirma el código de verificación.',
                        'codigo': 'mfa_requerido',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                verificado = servicio_mfa.verificar_desafio(mfa_token, codigo).usuario
            except servicio_mfa.MfaError as e:
                return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            # Un desafío es de quien lo abrió: otra cuenta no puede cerrarlo por esta.
            if verificado != usuario:
                return Response(
                    {'detail': 'La sesión de verificación expiró. Intenta de nuevo.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            servicio_cuenta.eliminar_cuenta(usuario)
        except ProtectedError:
            # Una suscripción de un contenedor que no es suyo todavía la referencia;
            # no se tocó nada.
            logger.warning('No se pudo eliminar la cuenta %s: tiene registros protegidos.', usuario.pk)
            return Response(
                {'detail': 'Tu cuenta tiene suscripciones asociadas y no se puede eliminar. '
                           'Escríbenos a soporte.'},
                status=status.HTTP_409_CONFLICT,
            )

        respuesta = Response(status=status.HTTP_204_NO_CONTENT)
        dominio = settings.AUTH_COOKIE_DOMAIN
        respuesta.delete_cookie('access_token', domain=dominio)
        respuesta.delete_cookie('refresh_token', domain=dominio)
        return respuesta

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
        except Exception as e:  # noqa: BLE001 — un envío que falla no tumba la petición
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
        except Exception as e:  # noqa: BLE001 — un envío que falla no tumba la petición
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
        except Exception as e:  # noqa: BLE001 — un envío que falla no tumba la petición
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
        # Una cuenta desactivada no puede entrar: no se ofrece para invitar.
        qs = SegUsuario.objects.filter(is_active=True).order_by('nombre_corto', 'email')
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
