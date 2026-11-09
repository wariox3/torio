from rest_framework import serializers

from contabilidad.models import ConExogenaDetalle


class ConExogenaDetalleSerializer(serializers.ModelSerializer):
    """
    Un formato de la exógena de un año. `cuantia_menor` es opcional al crear:
    si no llega, la vista copia la del formato.
    """

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'exogena_id', 'formato_id', 'estado_generado', 'estado_presentado'}
    select_related_lista = ('formato',)
    ordenamiento_default_lista = ('formato_id',)

    formato_nombre = serializers.CharField(source='formato.nombre', read_only=True, allow_null=True)

    class Meta:
        model = ConExogenaDetalle
        fields = [
            'id',
            'cuantia_menor',
            'fecha_generacion',
            'registros',
            'total',
            'estado_generado',
            'estado_presentado',
            'exogena',
            'formato',
            'formato_nombre',
        ]
        read_only_fields = [
            'id', 'fecha_generacion', 'registros', 'total', 'estado_generado', 'estado_presentado',
        ]
        # La unicidad (exógena, formato) la revisa la vista, con un mensaje propio.
        validators = []
