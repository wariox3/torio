from rest_framework import serializers


class SegUsuarioAplicacionSerializer(serializers.Serializer):
    """Una aplicación del catálogo y si el usuario la tiene activa."""

    aplicacion_id = serializers.IntegerField()
    aplicacion_nombre = serializers.CharField()
    activa = serializers.BooleanField()


class SegUsuarioAplicacionActualizarSerializer(serializers.Serializer):
    aplicaciones = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)
