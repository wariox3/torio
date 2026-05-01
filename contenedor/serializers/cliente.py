from rest_framework import serializers

from contenedor.models import CtnCliente


class CtnClienteSerializer(serializers.ModelSerializer):
    dominio = serializers.CharField(write_only=True)

    class Meta:
        model = CtnCliente
        fields = ['id', 'schema_name', 'nombre', 'activo', 'fecha_creacion', 'dominio']
        read_only_fields = ['id', 'activo', 'fecha_creacion']
