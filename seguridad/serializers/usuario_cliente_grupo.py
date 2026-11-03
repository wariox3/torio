from rest_framework import serializers

from seguridad.models import SegUsuarioCliente, SegUsuarioClienteGrupo


class SegUsuarioClienteGrupoSerializer(serializers.ModelSerializer):
    """Un grupo de un miembro en el contenedor, con su `heredar_permisos`."""

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'usuario_cliente_id', 'grupo_id', 'heredar_permisos'}
    select_related_lista = ('grupo',)
    ordenamiento_default_lista = ('grupo_id',)

    grupo_name = serializers.CharField(source='grupo.name', read_only=True, allow_null=True)

    class Meta:
        model = SegUsuarioClienteGrupo
        fields = ['id', 'usuario_cliente', 'grupo', 'grupo_name', 'heredar_permisos']
        read_only_fields = ['id']
        # El unique lo reporta validate() con `detail`, no con non_field_errors.
        validators = []

    def validate(self, attrs):
        membresia = attrs['usuario_cliente']
        # Una membresía de un contenedor al que no se pertenece se trata como inexistente.
        if not SegUsuarioCliente.objects.filter(
            usuario=self.context['request'].user, cliente_id=membresia.cliente_id,
        ).exists():
            raise serializers.ValidationError(
                {'detail': 'No se encontró el acceso de usuario a cliente.'}
            )
        if membresia.soporte:
            raise serializers.ValidationError(
                {'detail': 'Los grupos de un usuario de soporte no se modifican.'}
            )
        if SegUsuarioClienteGrupo.objects.filter(
            usuario_cliente=membresia, grupo=attrs['grupo'],
        ).exists():
            raise serializers.ValidationError({'detail': 'El usuario ya tiene ese grupo.'})
        return attrs
