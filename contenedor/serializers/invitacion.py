from django.contrib.auth.models import Group
from rest_framework import serializers

from contenedor.models import CtnCliente, CtnInvitacion
from seguridad.models import CAMPOS_ACCESO


class CtnInvitacionSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True)
    usuario_correo = serializers.CharField(source='usuario.email', read_only=True)
    grupos_nombres = serializers.SlugRelatedField(
        source='grupos', slug_field='name', many=True, read_only=True,
    )

    class Meta:
        model = CtnInvitacion
        fields = [
            'id', 'cliente', 'cliente_nombre',
            'usuario', 'usuario_nombre_corto', 'usuario_correo',
            'usuario_invitado',
            'grupos', 'grupos_nombres', 'estado', 'fecha',
            *CAMPOS_ACCESO,
        ]
        read_only_fields = ['id', 'cliente', 'cliente_nombre', 'usuario', 'usuario_nombre_corto', 'usuario_correo', 'usuario_invitado', 'grupos', 'estado', 'fecha', *CAMPOS_ACCESO]


class CtnInvitacionClienteSerializer(serializers.ModelSerializer):
    usuario_invitado_nombre_corto = serializers.CharField(source='usuario_invitado.nombre_corto', read_only=True)
    usuario_invitado_correo = serializers.CharField(source='usuario_invitado.email', read_only=True)
    grupos_nombres = serializers.SlugRelatedField(
        source='grupos', slug_field='name', many=True, read_only=True,
    )

    class Meta:
        model = CtnInvitacion
        fields = [
            'id', 'usuario_invitado', 'usuario_invitado_nombre_corto',
            'usuario_invitado_correo',
            'grupos', 'grupos_nombres', 'estado', 'fecha',
            *CAMPOS_ACCESO,
        ]
        read_only_fields = fields


class CtnInvitacionCrearSerializer(serializers.Serializer):
    cliente_id = serializers.PrimaryKeyRelatedField(
        queryset=CtnCliente.objects.all(),
        source='cliente',
    )
    usuario_id = serializers.IntegerField()
    # Los permisos reales. Opcional: se puede invitar sin grupos y otorgarlos
    # después sobre la membresía.
    grupo_ids = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        source='grupos',
        many=True,
        required=False,
        default=list,
    )

    # Módulos que verá el invitado en el menú. Todos opcionales y en False: si el
    # front no los manda, el usuario entra sin ninguna aplicación visible.
    acceso_venta = serializers.BooleanField(required=False, default=False)
    acceso_compra = serializers.BooleanField(required=False, default=False)
    acceso_tesoreria = serializers.BooleanField(required=False, default=False)
    acceso_cartera = serializers.BooleanField(required=False, default=False)
    acceso_inventario = serializers.BooleanField(required=False, default=False)
    acceso_humano = serializers.BooleanField(required=False, default=False)
    acceso_contabilidad = serializers.BooleanField(required=False, default=False)
    acceso_turno = serializers.BooleanField(required=False, default=False)
