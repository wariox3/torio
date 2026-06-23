from rest_framework import serializers

from general.models import GenContacto


class GenContactoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'nombre_corto', 'numero_identificacion',
        'cliente', 'proveedor', 'empleado', 'conductor', 'ciudad_id',
    }
    select_related_lista = ('identificacion', 'ciudad', 'tipo_persona', 'responsabilidad', 'banco')
    ordenamiento_default_lista = ('nombre_corto',)

    identificacion_nombre = serializers.CharField(source='identificacion.nombre', read_only=True)
    identificacion_abreviatura = serializers.CharField(source='identificacion.abreviatura', read_only=True)
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)
    tipo_persona_nombre = serializers.CharField(source='tipo_persona.nombre', read_only=True)
    responsabilidad_nombre = serializers.CharField(source='responsabilidad.nombre', read_only=True, default=None)
    banco_nombre = serializers.CharField(source='banco.nombre', read_only=True, default=None)

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
            'identificacion_abreviatura',
            'ciudad',
            'ciudad_nombre',
            'tipo_persona',
            'tipo_persona_nombre',
            'asesor',
            'precio',
            'plazo_pago',
            'plazo_pago_proveedor',
            'banco',
            'banco_nombre',
            'cuenta_banco_clase',
            'responsabilidad',
            'responsabilidad_nombre',
        ]
        read_only_fields = ['id']
