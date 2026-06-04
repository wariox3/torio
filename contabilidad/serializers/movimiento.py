from rest_framework import serializers

from contabilidad.models import ConMovimiento


class ConMovimientoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'numero', 'fecha', 'naturaleza', 'cierre', 'saldo_inicial',
        'comprobante', 'cuenta', 'grupo', 'periodo', 'contacto', 'documento',
    }
    select_related_lista = ('comprobante', 'cuenta', 'grupo', 'periodo', 'contacto', 'documento')
    ordenamiento_default_lista = ('-id',)

    comprobante_nombre = serializers.CharField(source='comprobante.nombre', read_only=True, default=None)
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, default=None)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, default=None)
    grupo_nombre = serializers.CharField(source='grupo.nombre', read_only=True, default=None)
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
            'grupo',
            'grupo_nombre',
            'periodo',
            'contacto',
            'contacto_nombre',
            'documento',
        ]
        read_only_fields = ['id']
