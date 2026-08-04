from rest_framework import serializers

from seguridad.models import SegRol


class SegRolSerializer(serializers.ModelSerializer):
    class Meta:
        model = SegRol
        fields = ['id', 'nombre', 'descripcion', 'activo', 'fecha_creacion']
        read_only_fields = ['id', 'fecha_creacion']
