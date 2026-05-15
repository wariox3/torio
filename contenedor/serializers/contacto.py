from rest_framework import serializers

from contenedor.models import CtnContacto


class CtnContactoSerializer(serializers.ModelSerializer):
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)

    class Meta:
        model = CtnContacto
        fields = [
            'id', 'numero_identificacion', 'digito_verificacion', 'nombre_corto',
            'direccion', 'telefono', 'correo',
            'identificacion', 'ciudad', 'ciudad_nombre', 'usuario',
        ]
        read_only_fields = ['id', 'usuario']


class CtnContactoListaUsuarioSerializer(serializers.ModelSerializer):
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)

    class Meta:
        model = CtnContacto
        fields = [
            'id', 'numero_identificacion', 'digito_verificacion', 'nombre_corto',
            'direccion', 'telefono', 'correo',
            'identificacion', 'ciudad', 'ciudad_nombre', 'usuario',
        ]
        read_only_fields = ['id', 'usuario']
