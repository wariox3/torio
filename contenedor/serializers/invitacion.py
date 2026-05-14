from rest_framework import serializers

from contenedor.models import CtnCliente, CtnInvitacion
from seguridad.models import SegRol


class CtnInvitacionSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True)
    usuario_correo = serializers.CharField(source='usuario.email', read_only=True)
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)

    class Meta:
        model = CtnInvitacion
        fields = [
            'id', 'cliente', 'cliente_nombre',
            'usuario', 'usuario_nombre_corto', 'usuario_correo',
            'usuario_invitado', 'rol', 'rol_nombre', 'estado', 'fecha',
        ]
        read_only_fields = ['id', 'cliente', 'cliente_nombre', 'usuario', 'usuario_nombre_corto', 'usuario_correo', 'usuario_invitado', 'estado', 'fecha']


class CtnInvitacionClienteSerializer(serializers.ModelSerializer):
    usuario_invitado_nombre_corto = serializers.CharField(source='usuario_invitado.nombre_corto', read_only=True)
    usuario_invitado_correo = serializers.CharField(source='usuario_invitado.email', read_only=True)
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)

    class Meta:
        model = CtnInvitacion
        fields = ['id', 'usuario_invitado', 'usuario_invitado_nombre_corto', 'usuario_invitado_correo', 'rol', 'rol_nombre', 'estado', 'fecha']
        read_only_fields = fields


class CtnInvitacionCrearSerializer(serializers.Serializer):
    cliente_id = serializers.PrimaryKeyRelatedField(
        queryset=CtnCliente.objects.all(),
        source='cliente',
    )
    usuario_id = serializers.IntegerField()
    rol_id = serializers.PrimaryKeyRelatedField(
        queryset=SegRol.objects.filter(activo=True),
        source='rol',
    )
