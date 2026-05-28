from rest_framework import serializers

from general.models import GenArchivo


class GenArchivoSerializer(serializers.ModelSerializer):
    archivo_tipo_codigo = serializers.CharField(source='archivo_tipo.codigo', read_only=True)
    archivo_tipo_nombre = serializers.CharField(source='archivo_tipo.nombre', read_only=True)
    modelo_app = serializers.CharField(source='modelo.app', read_only=True)
    modelo_clase = serializers.CharField(source='modelo.clase', read_only=True)

    class Meta:
        model = GenArchivo
        fields = [
            'id',
            'fecha',
            'archivo_tipo',
            'archivo_tipo_codigo',
            'archivo_tipo_nombre',
            'modelo',
            'modelo_app',
            'modelo_clase',
            'objeto_id',
            'nombre',
            'tipo',
            'tamano',
            'almacenamiento_id',
            'uuid',
            'url',
        ]
        read_only_fields = fields
