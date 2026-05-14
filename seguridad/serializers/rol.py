from rest_framework import serializers

from seguridad.models import SegPermiso, SegRol


class SegRolSerializer(serializers.ModelSerializer):
    permisos = serializers.PrimaryKeyRelatedField(
        many=True, queryset=SegPermiso.objects.all(), required=False,
    )
    permisos_codigos = serializers.SerializerMethodField()

    class Meta:
        model = SegRol
        fields = ['id', 'nombre', 'descripcion', 'activo', 'permisos', 'permisos_codigos', 'fecha_creacion']
        read_only_fields = ['id', 'fecha_creacion', 'permisos_codigos']

    def get_permisos_codigos(self, obj):
        return [p.codigo for p in obj.permisos.all()]
