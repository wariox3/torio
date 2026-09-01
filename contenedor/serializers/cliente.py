from rest_framework import serializers

from contenedor.models import CtnCliente, CtnDominio
from seguridad.models import SegUsuarioCliente
from utilidades.telefono import CampoTelefono


class CtnClienteSerializer(serializers.ModelSerializer):
    """
    El plan no se elige al crear el contenedor: todo tenant nuevo arranca en la
    suscripción de prueba que fija `CtnClienteViewSet.create`. Cambiarlo es cosa de
    `/contenedor/suscripcion/`, que sí valida tipo y frecuencia entre sí.
    """

    celular = CampoTelefono(label='Celular', max_length=20)

    class Meta:
        model = CtnCliente
        fields = [
            'id', 'schema_name', 'nombre', 'celular', 'correo', 'activo', 'fecha_creacion',
        ]
        read_only_fields = ['id', 'activo', 'fecha_creacion']


class CtnClienteActualizarSerializer(serializers.ModelSerializer):
    celular = CampoTelefono(label='Celular', max_length=20)

    class Meta:
        model = CtnCliente
        fields = ['nombre', 'correo', 'celular']


class CtnClienteListaUsuarioSerializer(serializers.ModelSerializer):
    cliente_id = serializers.IntegerField(source='cliente.id', read_only=True)
    schema_name = serializers.CharField(source='cliente.schema_name', read_only=True)
    nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    activo = serializers.BooleanField(source='cliente.activo', read_only=True)
    dominio = serializers.SerializerMethodField()
    suscripcion_id = serializers.IntegerField(source='cliente.suscripcion.id', read_only=True)
    suscripcion_fecha_fin = serializers.DateField(source='cliente.suscripcion.fecha_fin', read_only=True)
    suscripcion_frecuencia = serializers.CharField(source='cliente.suscripcion.frecuencia', read_only=True)
    suscripcion_suscripcion_tipo_nombre = serializers.CharField(
        source='cliente.suscripcion.suscripcion_tipo.nombre', read_only=True,
    )

    class Meta:
        model = SegUsuarioCliente
        fields = [
            'cliente_id', 'schema_name', 'nombre', 'activo', 'dominio',
            'suscripcion_id', 'suscripcion_fecha_fin', 'suscripcion_frecuencia',
            'suscripcion_suscripcion_tipo_nombre',
            'propietario',
            'acceso_venta', 'acceso_compra', 'acceso_tesoreria', 'acceso_cartera',
            'acceso_inventario', 'acceso_humano', 'acceso_contabilidad',
            'acceso_turno',
        ]

    def get_dominio(self, obj):
        dominios = getattr(obj.cliente, '_dominio_primario', None)
        if dominios is not None:
            return dominios[0].domain if dominios else None
        dominio = CtnDominio.objects.filter(tenant=obj.cliente, is_primary=True).first()
        return dominio.domain if dominio else None
