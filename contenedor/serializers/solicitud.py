from rest_framework import serializers

from contenedor.models import CtnCliente, CtnSolicitud


class CtnSolicitudSerializer(serializers.ModelSerializer):
    solicitud_tipo_nombre = serializers.CharField(source='solicitud_tipo.nombre', read_only=True)

    class Meta:
        model = CtnSolicitud
        fields = [
            'id', 'cliente', 'solicitud_tipo', 'solicitud_tipo_nombre', 'estado',
            'comentario', 'observacion', 'usuario', 'fecha_creacion', 'fecha_atencion',
        ]
        read_only_fields = [
            'id', 'estado', 'observacion', 'usuario', 'fecha_creacion', 'fecha_atencion',
        ]
        extra_kwargs = {'comentario': {'required': False, 'allow_null': True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo se puede pedir para un contenedor propio. Filtrar el queryset hace
        # que uno ajeno responda igual que uno que no existe: distinguirlos
        # confirmaría que el id es de alguien.
        request = self.context.get('request')
        if request is not None and 'cliente' in self.fields:
            self.fields['cliente'].queryset = CtnCliente.objects.filter(
                segusuariocliente__usuario=request.user,
            ).distinct()
