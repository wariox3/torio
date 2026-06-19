from rest_framework import serializers

from turno.models import TurPuesto


class TurPuestoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'nombre', 'estado_inactivo',
        'contacto', 'contacto__nombre_corto', 'contacto__numero_identificacion',
        'programador', 'ciudad', 'centro_costo',
    }
    select_related_lista = ('contacto', 'programador', 'ciudad', 'centro_costo')
    ordenamiento_default_lista = ('nombre',)

    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    programador_nombre = serializers.CharField(source='programador.nombre', read_only=True, default=None)
    ciudad_nombre = serializers.CharField(source='ciudad.nombre', read_only=True, default=None)
    centro_costo_nombre = serializers.CharField(source='centro_costo.nombre', read_only=True, default=None)

    class Meta:
        model = TurPuesto
        fields = [
            'id',
            'nombre',
            'direccion',
            'celular',
            'latitud',
            'longitud',
            'comentario',
            'estado_inactivo',
            'contacto',
            'contacto_nombre',
            'programador',
            'programador_nombre',
            'ciudad',
            'ciudad_nombre',
            'centro_costo',
            'centro_costo_nombre',
        ]
        read_only_fields = ['id']
