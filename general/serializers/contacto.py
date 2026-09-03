from rest_framework import serializers

from general.models import GenContacto
from utilidades.telefono import CampoTelefono


class GenContactoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'nombre_corto', 'numero_identificacion',
        'cliente', 'proveedor', 'empleado', 'conductor', 'ciudad_id',
    }
    select_related_lista = (
        'identificacion', 'ciudad', 'ciudad__estado', 'tipo_persona', 'responsabilidad',
        'banco', 'asesor', 'precio', 'plazo_pago', 'plazo_pago_proveedor',
    )
    ordenamiento_default_lista = ('nombre_corto',)

    celular = CampoTelefono(required=False, allow_null=True, max_length=50)
    identificacion_nombre = serializers.CharField(source='identificacion.nombre', read_only=True)
    identificacion_abreviatura = serializers.CharField(source='identificacion.abreviatura', read_only=True)
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True)
    departamento_nombre = serializers.CharField(source='ciudad.estado.nombre', read_only=True)
    tipo_persona_nombre = serializers.CharField(source='tipo_persona.nombre', read_only=True)
    responsabilidad_nombre = serializers.CharField(source='responsabilidad.nombre', read_only=True, default=None)
    banco_nombre = serializers.CharField(source='banco.nombre', read_only=True, default=None)
    asesor_nombre_corto = serializers.CharField(source='asesor.nombre_corto', read_only=True, default=None)
    precio_nombre = serializers.CharField(source='precio.nombre', read_only=True, default=None)
    plazo_pago_nombre = serializers.CharField(source='plazo_pago.nombre', read_only=True, default=None)
    plazo_pago_proveedor_nombre = serializers.CharField(
        source='plazo_pago_proveedor.nombre', read_only=True, default=None
    )

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
            'departamento_nombre',
            'tipo_persona',
            'tipo_persona_nombre',
            'asesor',
            'asesor_nombre_corto',
            'precio',
            'precio_nombre',
            'plazo_pago',
            'plazo_pago_nombre',
            'plazo_pago_proveedor',
            'plazo_pago_proveedor_nombre',
            'banco',
            'banco_nombre',
            'cuenta_banco_clase',
            'responsabilidad',
            'responsabilidad_nombre',
        ]
        read_only_fields = ['id']
