from rest_framework import serializers

from contabilidad.models import ConActivo


class ConActivoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'codigo', 'nombre', 'activo_grupo', 'metodo_depreciacion', 'grupo'}
    select_related_lista = (
        'activo_grupo', 'metodo_depreciacion', 'cuenta_gasto', 'cuenta_depreciacion', 'grupo',
    )
    ordenamiento_default_lista = ('-id',)

    activo_grupo_nombre = serializers.CharField(source='activo_grupo.nombre', read_only=True, default=None)
    metodo_depreciacion_nombre = serializers.CharField(source='metodo_depreciacion.nombre', read_only=True, default=None)
    cuenta_gasto_nombre = serializers.CharField(source='cuenta_gasto.nombre', read_only=True, default=None)
    cuenta_depreciacion_nombre = serializers.CharField(source='cuenta_depreciacion.nombre', read_only=True, default=None)
    grupo_nombre = serializers.CharField(source='grupo.nombre', read_only=True, default=None)

    class Meta:
        model = ConActivo
        fields = [
            'id',
            'codigo',
            'nombre',
            'marca',
            'serie',
            'modelo',
            'fecha_compra',
            'fecha_activacion',
            'fecha_baja',
            'duracion',
            'valor_compra',
            'depreciacion_inicial',
            'depreciacion_periodo',
            'depreciacion_acumulada',
            'depreciacion_saldo',
            'activo_grupo',
            'activo_grupo_nombre',
            'metodo_depreciacion',
            'metodo_depreciacion_nombre',
            'cuenta_gasto',
            'cuenta_gasto_nombre',
            'cuenta_depreciacion',
            'cuenta_depreciacion_nombre',
            'grupo',
            'grupo_nombre',
        ]
        read_only_fields = [
            'id',
            'depreciacion_periodo',
            'depreciacion_acumulada',
            'depreciacion_saldo',
        ]
