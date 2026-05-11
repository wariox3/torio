from rest_framework import serializers

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcionTipo


class CtnClienteSerializer(serializers.ModelSerializer):
    suscripcion_tipo_id = serializers.PrimaryKeyRelatedField(
        queryset=CtnSuscripcionTipo.objects.all(),
        write_only=True,
        source='suscripcion_tipo',
    )

    class Meta:
        model = CtnCliente
        fields = ['id', 'schema_name', 'nombre', 'telefono', 'correo', 'activo', 'fecha_creacion', 'suscripcion_tipo_id']
        read_only_fields = ['id', 'activo', 'fecha_creacion']


class CtnClienteListaUsuarioSerializer(serializers.ModelSerializer):
    dominio = serializers.SerializerMethodField()

    class Meta:
        model = CtnCliente
        fields = ['id', 'schema_name', 'nombre', 'activo', 'dominio']

    def get_dominio(self, obj):
        dominio = CtnDominio.objects.filter(tenant=obj, is_primary=True).first()
        return dominio.domain if dominio else None
