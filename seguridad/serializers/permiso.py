from rest_framework import serializers

from seguridad.models import SegPermiso


class SegPermisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SegPermiso
        fields = ['id', 'codigo', 'nombre', 'modulo', 'descripcion']
