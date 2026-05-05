from rest_framework import serializers

from seguridad.models import SegUsuario


class SegUsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

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
        user = SegUsuario(**validated_data)
        user.set_password(password)
        user.save()
        return user


class SegUsuarioActualizarSerializer(serializers.ModelSerializer):
    class Meta:
        model = SegUsuario
        fields = ['nombre_corto', 'numero_identificacion', 'celular', 'idioma']


class SegUsuarioMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SegUsuario
        fields = [
            'id', 'email', 'nombre_corto', 'numero_identificacion',
            'celular', 'idioma', 'imagen', 'imagen_thumbnail',
            'is_verified', 'fecha_creacion',
        ]
        read_only_fields = fields
