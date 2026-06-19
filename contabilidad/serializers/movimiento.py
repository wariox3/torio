from rest_framework import serializers

from contabilidad.models import ConMovimiento


class ConMovimientoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'numero', 'fecha', 'naturaleza', 'cierre', 'saldo_inicial',
        'comprobante', 'cuenta', 'centro_costo', 'periodo', 'documento',
        'contacto', 'contacto__nombre_corto', 'contacto__numero_identificacion',
    }
    select_related_lista = ('comprobante', 'cuenta', 'centro_costo', 'periodo', 'contacto', 'documento')
    ordenamiento_default_lista = ('-id',)

    comprobante_nombre = serializers.CharField(source='comprobante.nombre', read_only=True, default=None)
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, default=None)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, default=None)
    centro_costo_nombre = serializers.CharField(source='centro_costo.nombre', read_only=True, default=None)
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = ConMovimiento
        fields = [
            'id',
            'numero',
            'fecha',
            'debito',
            'credito',
            'base',
            'naturaleza',
            'detalle',
            'cierre',
            'saldo_inicial',
            'comprobante',
            'comprobante_nombre',
            'cuenta',
            'cuenta_codigo',
            'cuenta_nombre',
            'centro_costo',
            'centro_costo_nombre',
            'periodo',
            'contacto',
            'contacto_nombre',
            'documento',
        ]
        read_only_fields = ['id']
