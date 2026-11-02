from django.contrib.auth.models import Group
from rest_framework import serializers

from contenedor.models import CtnAplicacion, CtnCliente, CtnInvitacion


class CtnInvitacionSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True)
    usuario_email = serializers.CharField(source='usuario.email', read_only=True)
    grupos_nombres = serializers.SlugRelatedField(
        source='grupos', slug_field='name', many=True, read_only=True,
    )
    aplicaciones_nombres = serializers.SlugRelatedField(
        source='aplicaciones', slug_field='nombre', many=True, read_only=True,
    )

    class Meta:
        model = CtnInvitacion
        fields = [
            'id', 'cliente', 'cliente_nombre',
            'usuario', 'usuario_nombre_corto', 'usuario_email',
            'usuario_invitado',
            'grupos', 'grupos_nombres', 'aplicaciones', 'aplicaciones_nombres',
            'estado', 'fecha',
        ]
        read_only_fields = ['id', 'cliente', 'cliente_nombre', 'usuario', 'usuario_nombre_corto', 'usuario_email', 'usuario_invitado', 'grupos', 'aplicaciones', 'estado', 'fecha']


class CtnInvitacionClienteSerializer(serializers.ModelSerializer):
    usuario_invitado_nombre_corto = serializers.CharField(source='usuario_invitado.nombre_corto', read_only=True)
    usuario_invitado_correo = serializers.CharField(source='usuario_invitado.email', read_only=True)
    grupos_nombres = serializers.SlugRelatedField(
        source='grupos', slug_field='name', many=True, read_only=True,
    )
    aplicaciones_nombres = serializers.SlugRelatedField(
        source='aplicaciones', slug_field='nombre', many=True, read_only=True,
    )

    class Meta:
        model = CtnInvitacion
        fields = [
            'id', 'usuario_invitado', 'usuario_invitado_nombre_corto',
            'usuario_invitado_correo',
            'grupos', 'grupos_nombres', 'aplicaciones', 'aplicaciones_nombres',
            'estado', 'fecha',
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
    # Las aplicaciones que verá en el menú del contenedor. Obligatorio: sin al
    # menos una el invitado entraría sin ningún módulo visible.
    aplicacion_ids = serializers.PrimaryKeyRelatedField(
        queryset=CtnAplicacion.objects.all(),
        source='aplicaciones',
        many=True,
    )

    def validate_aplicacion_ids(self, valor):
        if not valor:
            raise serializers.ValidationError('Debe indicar al menos una aplicación.')
        return valor
