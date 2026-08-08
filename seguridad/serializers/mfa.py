from rest_framework import serializers

from seguridad.models import METODOS, SegMfaDispositivo


class SegMfaDispositivoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SegMfaDispositivo
        fields = ['id', 'user_agent', 'ip', 'ultimo_uso', 'expira']
        read_only_fields = fields


class SegMfaEstadoSerializer(serializers.Serializer):
    activo = serializers.BooleanField()
    metodo = serializers.CharField(allow_null=True)
    codigos_respaldo_restantes = serializers.IntegerField()
    dispositivos = SegMfaDispositivoSerializer(many=True)


class SegMfaConfigurarSerializer(serializers.Serializer):
    metodo = serializers.ChoiceField(choices=METODOS)


class SegMfaActivarSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    codigo = serializers.CharField()


class SegMfaDesactivarSerializer(serializers.Serializer):
    # Clave y código: desactivar el segundo factor exige los dos factores, o el más
    # débil bastaría para quitar al más fuerte.
    password = serializers.CharField(write_only=True)
    mfa_token = serializers.CharField()
    codigo = serializers.CharField()


class SegMfaClaveSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)


class SegMfaLoginSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    codigo = serializers.CharField()
    recordar_dispositivo = serializers.BooleanField(default=False)
