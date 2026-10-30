from datetime import date

from django.db import connection
from django_tenants.utils import get_public_schema_name
from rest_framework import serializers

from seguridad.foto import key_original, key_thumbnail, url_publica
from seguridad.models import SegUsuario
from utilidades.telefono import CampoTelefono


class SegUsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    celular = CampoTelefono(required=False, allow_null=True, max_length=50)

    class Meta:
        model = SegUsuario
        fields = [
            'id', 'email', 'password', 'nombre_corto',
            'numero_identificacion', 'celular', 'idioma',
            'is_active', 'fecha_creacion',
        ]
        read_only_fields = ['id', 'is_active', 'fecha_creacion']

    def create(self, validated_data):
        password = validated_data.pop('password')
        if not validated_data.get('nombre_corto'):
            validated_data['nombre_corto'] = validated_data['email'].split('@')[0]
        user = SegUsuario(**validated_data)
        user.set_password(password)
        user.save()
        return user


class SegUsuarioActualizarSerializer(serializers.ModelSerializer):
    celular = CampoTelefono(required=False, allow_null=True, max_length=50)

    class Meta:
        model = SegUsuario
        fields = ['nombre_corto', 'numero_identificacion', 'celular', 'idioma', 'fecha_nacimiento']

    def validate_fecha_nacimiento(self, valor):
        if valor is None:
            return valor
        if valor > date.today():
            raise serializers.ValidationError('La fecha de nacimiento no puede ser futura.')
        if valor.year < 1900:
            raise serializers.ValidationError('La fecha de nacimiento no es válida.')
        return valor


class SegUsuarioSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = SegUsuario
        fields = ['id', 'nombre_corto', 'email']


class SegUsuarioMeSerializer(serializers.ModelSerializer):
    imagen = serializers.SerializerMethodField()
    imagen_thumbnail = serializers.SerializerMethodField()
    mfa_activo = serializers.SerializerMethodField()
    mfa_metodo = serializers.SerializerMethodField()
    is_staff = serializers.SerializerMethodField()

    class Meta:
        model = SegUsuario
        fields = [
            'id', 'email', 'nombre_corto', 'numero_identificacion',
            'celular', 'idioma', 'fecha_nacimiento', 'imagen', 'imagen_thumbnail',
            'is_verified', 'mfa_activo', 'mfa_metodo',
            'is_staff', 'fecha_creacion',
        ]
        read_only_fields = fields

    def get_is_staff(self, obj) -> bool:
        """
        Si es staff de la plataforma: el front lo usa para mostrar el panel de
        administración, que igual protege `EsStaff`.

        `is_staff` sale de los permisos del usuario en el tenant activo, así que
        solo vale en el schema público; en cualquier otro diría si es staff de ese
        contenedor, y se responde `False`.
        """
        tenant = connection.tenant
        if tenant is not None and tenant.schema_name != get_public_schema_name():
            return False
        return bool(obj.is_staff)

    def _mfa(self, obj):
        # La 1-1 puede no existir: la mayoría de cuentas no tiene MFA configurado.
        mfa = getattr(obj, 'mfa', None)
        return mfa if mfa and mfa.activo else None

    def get_mfa_activo(self, obj) -> bool:
        return self._mfa(obj) is not None

    def get_mfa_metodo(self, obj) -> str | None:
        mfa = self._mfa(obj)
        return mfa.metodo if mfa else None

    def get_imagen(self, obj) -> str | None:
        if not obj.imagen_uuid:
            return None
        return url_publica(key_original(obj.id, obj.imagen_uuid))

    def get_imagen_thumbnail(self, obj) -> str | None:
        # Null cuando no hay foto, en vez de la URL de una imagen por defecto:
        # el front sabe mejor qué poner (iniciales, avatar genérico) y así no se
        # pide a B2 un objeto que puede no existir.
        if not obj.imagen_uuid:
            return None
        return url_publica(key_thumbnail(obj.id, obj.imagen_uuid))
