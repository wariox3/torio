from rest_framework import serializers

from contenedor.models import CtnContacto
from utilidades.telefono import CampoTelefono


class CtnContactoSerializer(serializers.ModelSerializer):
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)
    celular = CampoTelefono(max_length=50)

    class Meta:
        model = CtnContacto
        fields = [
            'id', 'numero_identificacion', 'digito_verificacion', 'nombre_corto',
            'direccion', 'celular', 'correo',
            'identificacion', 'ciudad', 'ciudad_nombre', 'usuario',
        ]
        read_only_fields = ['id', 'usuario']


class CtnContactoListaUsuarioSerializer(serializers.ModelSerializer):
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)
    departamento_nombre = serializers.CharField(source='ciudad.estado.nombre', read_only=True)
    celular = CampoTelefono(max_length=50)

    class Meta:
        model = CtnContacto
        fields = [
            'id', 'numero_identificacion', 'digito_verificacion', 'nombre_corto',
            'direccion', 'celular', 'correo',
            'identificacion', 'ciudad', 'ciudad_nombre', 'departamento_nombre', 'usuario',
        ]
        read_only_fields = ['id', 'usuario']
