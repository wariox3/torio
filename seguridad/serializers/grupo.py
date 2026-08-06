from django.contrib.auth.models import Group
from rest_framework import serializers


class SegGrupoSerializer(serializers.ModelSerializer):
    """Grupo de permisos. `name` se expone además como `nombre` por coherencia
    con el resto de la API, que está en español."""

    nombre = serializers.CharField(source='name', read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'nombre']
        read_only_fields = fields


class SegGrupoPermisoSerializer(serializers.Serializer):
    """Solo para documentación del schema."""

    app = serializers.CharField()
    modelo = serializers.CharField()
    accion = serializers.CharField()
    codename = serializers.CharField()


class SegGrupoDetalleSerializer(SegGrupoSerializer):
    """Grupo con el desglose de sus permisos, para pantallas de administración."""

    permisos = serializers.SerializerMethodField()

    class Meta(SegGrupoSerializer.Meta):
        fields = ['id', 'nombre', 'permisos']
        read_only_fields = fields

    def get_permisos(self, obj):
        return [
            {
                'app': permiso.content_type.app_label,
                'modelo': permiso.content_type.model,
                # El codename es '<accion>_<modelo>'; la acción es lo que va antes.
                'accion': permiso.codename.rsplit(f'_{permiso.content_type.model}', 1)[0],
                'codename': permiso.codename,
            }
            for permiso in obj.permissions.select_related('content_type').order_by('codename')
        ]
