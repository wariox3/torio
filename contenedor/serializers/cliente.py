from rest_framework import serializers

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo


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
        fields = ['nombre']


class CtnClienteListaUsuarioSerializer(serializers.ModelSerializer):
    dominio = serializers.SerializerMethodField()
    suscripcion_id = serializers.IntegerField(source='suscripcion.id', read_only=True)
    suscripcion_fecha_fin = serializers.DateField(source='suscripcion.fecha_fin', read_only=True)
    suscripcion_frecuencia = serializers.CharField(source='suscripcion.frecuencia', read_only=True)
    suscripcion_suscripcion_tipo_nombre = serializers.CharField(
        source='suscripcion.suscripcion_tipo.nombre', read_only=True,
    )

    class Meta:
        model = CtnCliente
        fields = [
            'id', 'schema_name', 'nombre', 'activo', 'dominio',
            'suscripcion_id', 'suscripcion_fecha_fin', 'suscripcion_frecuencia',
            'suscripcion_suscripcion_tipo_nombre',
        ]

    def get_dominio(self, obj):
        dominios = getattr(obj, '_dominio_primario', None)
        if dominios is not None:
            return dominios[0].domain if dominios else None
        dominio = CtnDominio.objects.filter(tenant=obj, is_primary=True).first()
        return dominio.domain if dominio else None
