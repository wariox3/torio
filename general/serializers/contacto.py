from rest_framework import serializers

from general.models import GenContacto


class GenContactoSerializer(serializers.ModelSerializer):
    identificacion_nombre = serializers.CharField(source='identificacion.nombre', read_only=True)
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)
    tipo_persona_nombre = serializers.CharField(source='tipo_persona.nombre', read_only=True)

    class Meta:
        model = GenContacto
        fields = [
            'id',
            'numero_identificacion',
            'digito_verificacion',
            'nombre_corto',
            'nombre1',
            'nombre2',
            'apellido1',
            'apellido2',
            'direccion',
            'barrio',
            'codigo_ciuu',
            'codigo_postal',
            'telefono',
            'celular',
            'correo',
            'correo_facturacion_electronica',
            'cliente',
            'proveedor',
            'empleado',
            'conductor',
            'numero_cuenta',
            'numero_licencia',
            'fecha_vence_licencia',
            'identificacion',
            'identificacion_nombre',
            'ciudad',
            'ciudad_nombre',
            'tipo_persona',
            'tipo_persona_nombre',
            'asesor',
            'precio',
            'plazo_pago',
            'plazo_pago_proveedor',
            'banco',
            'cuenta_banco_clase',
        ]
        read_only_fields = ['id']
