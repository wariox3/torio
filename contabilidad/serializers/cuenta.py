from rest_framework import serializers

from contabilidad.models import ConCuenta


class ConCuentaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'codigo', 'nombre', 'nivel',
        'exige_base', 'exige_contacto', 'exige_grupo', 'permite_movimiento',
        'cuenta_clase', 'cuenta_grupo', 'cuenta_cuenta', 'cuenta_subcuenta',
    }
    select_related_lista = (
        'cuenta_clase', 'cuenta_grupo', 'cuenta_cuenta', 'cuenta_subcuenta',
    )
    ordenamiento_default_lista = ('codigo',)

    cuenta_clase_nombre = serializers.CharField(source='cuenta_clase.nombre', read_only=True)
    cuenta_grupo_nombre = serializers.CharField(source='cuenta_grupo.nombre', read_only=True)
    cuenta_cuenta_nombre = serializers.CharField(source='cuenta_cuenta.nombre', read_only=True)
    cuenta_subcuenta_nombre = serializers.CharField(source='cuenta_subcuenta.nombre', read_only=True)

    class Meta:
        model = ConCuenta
        fields = [
            'id',
            'codigo',
            'nombre',
            'exige_base',
            'exige_contacto',
            'exige_grupo',
            'permite_movimiento',
            'nivel',
            'cuenta_clase',
            'cuenta_clase_nombre',
            'cuenta_grupo',
            'cuenta_grupo_nombre',
            'cuenta_cuenta',
            'cuenta_cuenta_nombre',
            'cuenta_subcuenta',
            'cuenta_subcuenta_nombre',
        ]
        read_only_fields = ['id']
