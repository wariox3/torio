from rest_framework import serializers

from contabilidad.models import ConConciliacionDetalle


class ConConciliacionDetalleSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'conciliacion', 'cuenta', 'contacto', 'documento', 'estado_conciliado'}
    select_related_lista = ('conciliacion', 'cuenta', 'contacto', 'documento')
    ordenamiento_default_lista = ('-id',)

    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, default=None)
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = ConConciliacionDetalle
        fields = [
            'id',
            'fecha',
            'debito',
            'credito',
            'detalle',
            'estado_conciliado',
            'conciliacion',
            'cuenta',
            'cuenta_nombre',
            'contacto',
            'contacto_nombre',
            'documento',
        ]
        read_only_fields = ['id']
