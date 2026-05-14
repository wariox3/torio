from rest_framework import serializers

from contenedor.models import CtnCliente, CtnInvitacion
from seguridad.models import SegRol


class CtnInvitacionSerializer(serializers.ModelSerializer):
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)

    class Meta:
        model = CtnInvitacion
        fields = ['id', 'usuario_invitado', 'rol', 'rol_nombre', 'estado', 'fecha']
        read_only_fields = ['id', 'usuario_invitado', 'estado', 'fecha']


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
