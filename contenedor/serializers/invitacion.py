from rest_framework import serializers

from contenedor.models import CtnCliente, CtnInvitacion


class CtnInvitacionSerializer(serializers.ModelSerializer):
    cliente_id = serializers.PrimaryKeyRelatedField(
        queryset=CtnCliente.objects.all(),
        source='cliente',
        write_only=True,
    )

    class Meta:
        model = CtnInvitacion
        fields = ['id', 'cliente_id', 'correo', 'estado', 'fecha_envio', 'fecha_expira']
        read_only_fields = ['id', 'estado', 'fecha_envio', 'fecha_expira']


class CtnInvitacionAceptarSerializer(serializers.Serializer):
    token = serializers.CharField()
