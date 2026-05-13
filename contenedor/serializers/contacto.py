from rest_framework import serializers

from contenedor.models import CtnContacto


class CtnContactoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnContacto
        fields = [
            'id', 'numero_identificacion', 'digito_verificacion', 'nombre_corto',
            'direccion', 'telefono', 'correo',
            'identificacion', 'ciudad', 'usuario',
        ]
        read_only_fields = ['id', 'usuario']
        read_only_fields = ['id', 'usuario']
