from rest_framework import serializers

from general.models import GenLog


class GenLogSerializer(serializers.ModelSerializer):
    accion_codigo = serializers.CharField(source='accion.codigo', read_only=True)
    accion_nombre = serializers.CharField(source='accion.nombre', read_only=True)
    modelo_app = serializers.CharField(source='modelo.app', read_only=True)
    modelo_clase = serializers.CharField(source='modelo.clase', read_only=True)
    modelo_nombre = serializers.CharField(source='modelo.nombre', read_only=True)

    class Meta:
        model = GenLog
        fields = [
            'id',
            'fecha',
            'accion',
            'accion_codigo',
            'accion_nombre',
            'modelo',
            'modelo_app',
            'modelo_clase',
            'modelo_nombre',
            'objeto_id',
            'datos',
            'usuario_id',
            'usuario_correo',
        ]
