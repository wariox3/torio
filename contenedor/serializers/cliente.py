from rest_framework import serializers

from contenedor.models import CtnCliente, CtnDominio


class CtnClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnCliente
        fields = ['id', 'schema_name', 'nombre', 'telefono', 'correo', 'activo', 'fecha_creacion']
        read_only_fields = ['id', 'activo', 'fecha_creacion']


class CtnClienteListaUsuarioSerializer(serializers.ModelSerializer):
    dominio = serializers.SerializerMethodField()

    class Meta:
        model = CtnCliente
        fields = ['id', 'schema_name', 'nombre', 'activo', 'dominio']

    def get_dominio(self, obj):
        dominio = CtnDominio.objects.filter(tenant=obj, is_primary=True).first()
        return dominio.domain if dominio else None
