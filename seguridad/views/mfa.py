from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone

from seguridad import mfa as servicio_mfa
from seguridad.models import (
    METODO_SMS,
    METODO_TOTP,
    METODOS_ENVIADOS,
    SegMfaCodigoRespaldo,
    SegMfaUsuario,
)
from seguridad.serializers import (
    SegMfaActivarSerializer,
    SegMfaClaveSerializer,
    SegMfaConfigurarSerializer,
    SegMfaDesactivarSerializer,
    SegMfaDispositivoSerializer,
    SegMfaEstadoSerializer,
)

_RespuestaDetalle = inline_serializer(
    name='MfaDetailResponse',
    fields={'detail': serializers.CharField()},
)


@extend_schema(tags=['MFA'])
class SegMfaViewSet(viewsets.ViewSet):
    """
    Segundo factor de la cuenta autenticada.

    Todas las acciones son sobre el propio usuario: no hay forma de administrar el MFA
    de un tercero, ni siquiera siendo propietario de un contenedor. El MFA es de la
    cuenta, no de la organización.
    """

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        scopes = {
            'configurar': 'mfa_gestion',
            'activar': 'mfa_gestion',
            'desactivar': 'mfa_gestion',
            'codigos_respaldo': 'mfa_gestion',
            'desafio': 'mfa_envio_codigo',
        }
        if self.action in scopes:
            self.throttle_scope = scopes[self.action]
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @extend_schema(
        summary='Estado del segundo factor',
        description='Indica si está activo, con qué método, cuántos códigos de respaldo quedan y qué dispositivos están recordados.',
        responses={200: SegMfaEstadoSerializer},
    )
    def list(self, request):
        mfa = SegMfaUsuario.objects.filter(usuario=request.user).first()
        datos = {
            'activo': bool(mfa and mfa.activo),
            'metodo': mfa.metodo if mfa and mfa.activo else None,
            'codigos_respaldo_restantes': servicio_mfa.codigos_respaldo_restantes(request.user),
            'dispositivos': SegMfaDispositivoSerializer(
                request.user.dispositivos_mfa.filter(expira__gt=timezone.now()), many=True
            ).data,
        }
        return Response(datos)

    @extend_schema(
        summary='Iniciar configuración',
        description=(
            'Prepara el segundo factor sin activarlo todavía. Con `totp` devuelve el URI '
            '`otpauth://` para el QR y el secreto en texto por si el usuario no puede escanear. '
            'Con `correo` envía un código. En ambos casos devuelve el `mfa_token` que espera `activar`.'
        ),
        request=SegMfaConfigurarSerializer,
        responses={
            200: inline_serializer(
                name='MfaConfigurarResponse',
                fields={
                    'mfa_token': serializers.CharField(),
                    'metodo': serializers.CharField(),
                    'otpauth_uri': serializers.CharField(required=False),
                    'secreto': serializers.CharField(required=False),
                },
            ),
            400: OpenApiResponse(_RespuestaDetalle, description='El MFA ya está activo'),
        },
    )
    @action(detail=False, methods=['post'])
    def configurar(self, request):
        serializador = SegMfaConfigurarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        metodo = serializador.validated_data['metodo']

        # Reconfigurar con el MFA prendido dejaría una ventana en la que conviven dos
        # factores válidos. Primero se desactiva —que exige clave y código— y luego se
        # vuelve a configurar.
        if SegMfaUsuario.objects.filter(usuario=request.user, activo=True).exists():
            return Response(
                {'detail': 'Ya tienes la verificación en dos pasos activa. Desactívala antes de reconfigurarla.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Se valida antes de crear nada: si el celular no sirve, el usuario no recibiría
        # el código y quedaría con una configuración pendiente que no puede confirmar.
        if metodo == METODO_SMS and not servicio_mfa.celular_para_sms(request.user):
            return Response(
                {'detail': 'Registra un número de celular válido de 10 dígitos en tu perfil antes de usar SMS.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        secreto = servicio_mfa.generar_secreto() if metodo == METODO_TOTP else None
        SegMfaUsuario.objects.update_or_create(
            usuario=request.user,
            defaults={
                'metodo': metodo,
                'secreto': servicio_mfa.cifrar_secreto(secreto) if secreto else None,
                'activo': False,
                # Se reinicia con cada configuración: el contador viejo pertenece a un
                # secreto que ya no existe.
                'ultimo_contador': None,
                'fecha_activacion': None,
            },
        )

        desafio, codigo = servicio_mfa.crear_desafio(request.user, metodo, self._ip(request))
        datos = {'mfa_token': servicio_mfa.firmar_desafio(desafio), 'metodo': metodo}

        if metodo == METODO_TOTP:
            datos['otpauth_uri'] = servicio_mfa.uri_otpauth(request.user, secreto)
            datos['secreto'] = secreto
        else:
            servicio_mfa.enviar_codigo(request.user, codigo, metodo)

        return Response(datos)

    @extend_schema(
        summary='Activar el segundo factor',
        description=(
            'Confirma la configuración con un código y la deja activa. Devuelve los códigos '
            'de respaldo **una sola vez**: después solo queda su hash. Cierra las demás sesiones.'
        ),
        request=SegMfaActivarSerializer,
        responses={
            200: inline_serializer(
                name='MfaActivarResponse',
                fields={
                    'detail': serializers.CharField(),
                    'codigos_respaldo': serializers.ListField(child=serializers.CharField()),
                },
            ),
            400: OpenApiResponse(_RespuestaDetalle, description='Código inválido o configuración inexistente'),
        },
    )
    @action(detail=False, methods=['post'])
    def activar(self, request):
        serializador = SegMfaActivarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        mfa = SegMfaUsuario.objects.filter(usuario=request.user).first()
        if mfa is None:
            return Response(
                {'detail': 'Primero configura la verificación en dos pasos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if mfa.activo:
            return Response(
                {'detail': 'La verificación en dos pasos ya está activa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sin códigos de respaldo: acá se está probando que el factor nuevo funciona, y
        # un código de respaldo viejo no prueba nada de eso.
        usuario = self._verificar(request, serializador.validated_data, permitir_respaldo=False)
        if isinstance(usuario, Response):
            return usuario

        mfa.activo = True
        mfa.fecha_activacion = timezone.now()
        mfa.save(update_fields=['activo', 'fecha_activacion'])

        codigos = servicio_mfa.generar_codigos_respaldo(request.user)
        servicio_mfa.olvidar_dispositivos(request.user)
        servicio_mfa.invalidar_sesiones(request.user)

        return Response({
            'detail': 'Verificación en dos pasos activada. Guarda los códigos de respaldo: no se vuelven a mostrar.',
            'codigos_respaldo': codigos,
        })

    @extend_schema(
        summary='Pedir un código para una operación sensible',
        description=(
            'Abre un desafío contra el MFA ya activo, para operaciones que exigen volver a '
            'probar el segundo factor (hoy: desactivar). Con método `correo` envía el código.'
        ),
        request=None,
        responses={
            200: inline_serializer(
                name='MfaDesafioResponse',
                fields={'mfa_token': serializers.CharField(), 'metodo': serializers.CharField()},
            ),
            400: OpenApiResponse(_RespuestaDetalle, description='El MFA no está activo'),
        },
    )
    @action(detail=False, methods=['post'])
    def desafio(self, request):
        mfa = servicio_mfa.mfa_activo(request.user)
        if mfa is None:
            return Response(
                {'detail': 'No tienes la verificación en dos pasos activa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        desafio, codigo = servicio_mfa.crear_desafio(request.user, mfa.metodo, self._ip(request))
        if mfa.metodo in METODOS_ENVIADOS:
            servicio_mfa.enviar_codigo(request.user, codigo, mfa.metodo)

        return Response({'mfa_token': servicio_mfa.firmar_desafio(desafio), 'metodo': mfa.metodo})

    @extend_schema(
        summary='Desactivar el segundo factor',
        description='Exige clave y código (o código de respaldo). Borra la configuración, los códigos y los dispositivos recordados.',
        request=SegMfaDesactivarSerializer,
        responses={
            200: _RespuestaDetalle,
            400: OpenApiResponse(_RespuestaDetalle, description='Clave o código inválidos'),
        },
    )
    @action(detail=False, methods=['post'])
    def desactivar(self, request):
        serializador = SegMfaDesactivarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        if not request.user.check_password(serializador.validated_data['password']):
            return Response({'detail': 'La clave es incorrecta.'}, status=status.HTTP_400_BAD_REQUEST)

        if not SegMfaUsuario.objects.filter(usuario=request.user, activo=True).exists():
            return Response(
                {'detail': 'No tienes la verificación en dos pasos activa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario = self._verificar(request, serializador.validated_data)
        if isinstance(usuario, Response):
            return usuario

        SegMfaCodigoRespaldo.objects.filter(usuario=request.user).delete()
        SegMfaUsuario.objects.filter(usuario=request.user).delete()
        servicio_mfa.olvidar_dispositivos(request.user)
        servicio_mfa.invalidar_sesiones(request.user)

        return Response({'detail': 'Verificación en dos pasos desactivada.'})

    @extend_schema(
        summary='Regenerar códigos de respaldo',
        description='Invalida los códigos anteriores y devuelve diez nuevos, **una sola vez**.',
        request=SegMfaClaveSerializer,
        responses={
            200: inline_serializer(
                name='MfaCodigosRespaldoResponse',
                fields={'codigos_respaldo': serializers.ListField(child=serializers.CharField())},
            ),
            400: OpenApiResponse(_RespuestaDetalle, description='Clave incorrecta o MFA inactivo'),
        },
    )
    @action(detail=False, methods=['post'], url_path='codigos-respaldo')
    def codigos_respaldo(self, request):
        serializador = SegMfaClaveSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        if not request.user.check_password(serializador.validated_data['password']):
            return Response({'detail': 'La clave es incorrecta.'}, status=status.HTTP_400_BAD_REQUEST)

        if servicio_mfa.mfa_activo(request.user) is None:
            return Response(
                {'detail': 'No tienes la verificación en dos pasos activa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'codigos_respaldo': servicio_mfa.generar_codigos_respaldo(request.user)})

    @extend_schema(
        summary='Revocar un dispositivo recordado',
        description='Ese navegador vuelve a pedir el código en el siguiente login.',
        responses={
            204: None,
            404: OpenApiResponse(_RespuestaDetalle, description='Dispositivo no encontrado'),
        },
    )
    @action(detail=False, methods=['delete'], url_path=r'dispositivo/(?P<dispositivo_id>\d+)')
    def dispositivo(self, request, dispositivo_id=None):
        # Filtrado por usuario: un id ajeno responde 404, no borra nada de otra cuenta.
        borrados, _ = request.user.dispositivos_mfa.filter(pk=dispositivo_id).delete()
        if not borrados:
            return Response({'detail': 'Dispositivo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _verificar(self, request, datos, permitir_respaldo=True):
        """
        Resuelve un desafío y confirma que es del usuario de la petición.

        Devuelve el usuario, o la `Response` de error lista para retornar.
        """
        try:
            usuario = servicio_mfa.verificar_desafio(
                datos['mfa_token'], datos['codigo'], permitir_respaldo=permitir_respaldo
            )
        except servicio_mfa.MfaError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Un desafío es de quien lo abrió. Sin esto, quien tenga sesión propia podría
        # cerrar con su token el desafío de otra cuenta.
        if usuario != request.user:
            return Response(
                {'detail': 'La sesión de verificación expiró. Intenta de nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return usuario

    @staticmethod
    def _ip(request):
        return request.META.get('REMOTE_ADDR')
