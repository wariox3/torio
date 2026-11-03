from rest_framework import serializers

from seguridad.models import SegUsuarioCliente, SegUsuarioClientePermiso


class SegUsuarioClientePermisoSerializer(serializers.ModelSerializer):
    """Un permiso personalizado de un miembro, con el permiso desglosado."""

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'usuario_cliente_id', 'permiso_id'}
    select_related_lista = ('permiso__content_type',)
    ordenamiento_default_lista = (
        'permiso__content_type__app_label', 'permiso__content_type__model', 'permiso__codename',
    )

    permiso_codename = serializers.CharField(
        source='permiso.codename', read_only=True, allow_null=True,
    )
    permiso_name = serializers.CharField(source='permiso.name', read_only=True, allow_null=True)
    permiso_content_type_app_label = serializers.CharField(
        source='permiso.content_type.app_label', read_only=True, allow_null=True,
    )
    permiso_content_type_model = serializers.CharField(
        source='permiso.content_type.model', read_only=True, allow_null=True,
    )

    class Meta:
        model = SegUsuarioClientePermiso
        fields = [
            'id',
            'usuario_cliente',
            'permiso',
            'permiso_codename',
            'permiso_name',
            'permiso_content_type_app_label',
            'permiso_content_type_model',
        ]
        read_only_fields = ['id']
        # El unique lo reporta validate() con `detail`, no con non_field_errors.
        validators = []

    def validate(self, attrs):
        # Importado acá: seguridad.views importa este módulo.
        from seguridad.views.permiso import apps_asignables

        membresia = attrs['usuario_cliente']
        permiso = attrs['permiso']
        # Una membresía de un contenedor al que no se pertenece se trata como inexistente.
        if not SegUsuarioCliente.objects.filter(
            usuario=self.context['request'].user, cliente_id=membresia.cliente_id,
        ).exists():
            raise serializers.ValidationError(
                {'detail': 'No se encontró el acceso de usuario a cliente.'}
            )
        if membresia.soporte:
            raise serializers.ValidationError(
                {'detail': 'Los permisos de un usuario de soporte no se modifican.'}
            )
        if permiso.content_type.app_label not in apps_asignables():
            raise serializers.ValidationError(
                {'detail': f'El permiso {permiso.codename} no es asignable.'}
            )
        if SegUsuarioClientePermiso.objects.filter(
            usuario_cliente=membresia, permiso=permiso,
        ).exists():
            raise serializers.ValidationError({'detail': 'El usuario ya tiene ese permiso.'})
        return attrs
