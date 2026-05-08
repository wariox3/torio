from rest_framework import serializers

from contenedor.models import CtnDatosFacturacion


class CtnDatosFacturacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnDatosFacturacion
        fields = [
            'id', 'numero_identificacion', 'digito_verificacion', 'nombre_corto',
            'direccion', 'telefono', 'correo',
            'identificacion', 'ciudad', 'usuario',
        ]
