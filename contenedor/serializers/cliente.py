from rest_framework import serializers

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo
from seguridad.models import SegUsuarioCliente


class CtnClienteSerializer(serializers.ModelSerializer):
    suscripcion_tipo_id = serializers.PrimaryKeyRelatedField(
        queryset=CtnSuscripcionTipo.objects.all(),
        write_only=True,
        source='suscripcion_tipo',
    )
    frecuencia = serializers.ChoiceField(
        choices=CtnSuscripcion.FRECUENCIA_CHOICES,
        write_only=True,
    )

    class Meta:
        model = CtnCliente
        fields = [
            'id', 'schema_name', 'nombre', 'telefono', 'correo', 'activo', 'fecha_creacion',
            'suscripcion_tipo_id', 'frecuencia',
        ]
        read_only_fields = ['id', 'activo', 'fecha_creacion']

    def validate(self, attrs):
        suscripcion_tipo = attrs.get('suscripcion_tipo')
        frecuencia = attrs.get('frecuencia')
        if suscripcion_tipo and frecuencia:
            if suscripcion_tipo.suscripcion_categoria_id == 99:
                if frecuencia != CtnSuscripcion.FRECUENCIA_PRUEBA:
                    raise serializers.ValidationError(
                        {'frecuencia': 'Para categoría 99 la frecuencia debe ser P (Prueba).'}
                    )
            else:
                if frecuencia not in (CtnSuscripcion.FRECUENCIA_MENSUAL, CtnSuscripcion.FRECUENCIA_ANUAL):
                    raise serializers.ValidationError(
                        {'frecuencia': 'La frecuencia debe ser M (Mensual) o A (Anual).'}
                    )
        return attrs


class CtnClienteActualizarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnCliente
        fields = ['nombre', 'correo', 'telefono']


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
    rol_id = serializers.IntegerField(source='rol.id', read_only=True)
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)

    class Meta:
        model = SegUsuarioCliente
        fields = [
            'cliente_id', 'schema_name', 'nombre', 'activo', 'dominio',
            'suscripcion_id', 'suscripcion_fecha_fin', 'suscripcion_frecuencia',
            'suscripcion_suscripcion_tipo_nombre',
            'rol_id', 'rol_nombre',
        ]

    def get_dominio(self, obj):
        dominios = getattr(obj.cliente, '_dominio_primario', None)
        if dominios is not None:
            return dominios[0].domain if dominios else None
        dominio = CtnDominio.objects.filter(tenant=obj.cliente, is_primary=True).first()
        return dominio.domain if dominio else None
