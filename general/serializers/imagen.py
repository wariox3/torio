from rest_framework import serializers

from general.models import GenImagen, GenModelo
from general.servicios import imagen as imagen_servicio


class GenImagenSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    url_miniatura = serializers.SerializerMethodField()

    class Meta:
        model = GenImagen
        fields = [
            'id',
            'fecha',
            'modelo',
            'objeto_id',
            'uuid',
            'principal',
            'url',
            'url_miniatura',
        ]
        read_only_fields = fields

    def get_url(self, obj) -> str | None:
        return imagen_servicio.url_original(obj.uuid)

    def get_url_miniatura(self, obj) -> str | None:
        return imagen_servicio.url_miniatura(obj.uuid)


class GenImagenCrearSerializer(serializers.Serializer):
    """
    Valida la entrada de `POST /general/imagen/`.

    Solo la forma: que la imagen sirva y que el registro exista lo decide
    `general.servicios.imagen.subir_imagen`, que es quien la abre.
    """

    # En multipart todo llega como texto; ver `GenArchivoCrearSerializer`.
    _NO_ENTERO = {
        'incorrect_type': 'Debe ser un número entero.',
        'invalid': 'Debe ser un número entero.',
    }

    imagen = serializers.FileField()
    modelo = serializers.PrimaryKeyRelatedField(
        queryset=GenModelo.objects.all(),
        error_messages=_NO_ENTERO,
    )
    objeto_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
        error_messages=_NO_ENTERO,
    )


class ImagenPrincipalSerializerMixin(serializers.Serializer):
    """
    Agrega la imagen principal del registro a su serializer.

    El viewset debe pasar su queryset por `anotar_imagen_principal`; sin eso
    funciona igual, pero con una consulta por fila.
    """

    imagen_principal_url = serializers.SerializerMethodField()
    imagen_principal_url_miniatura = serializers.SerializerMethodField()

    def get_imagen_principal_url(self, obj) -> str | None:
        return imagen_servicio.url_original(imagen_servicio.uuid_principal(obj))

    def get_imagen_principal_url_miniatura(self, obj) -> str | None:
        return imagen_servicio.url_miniatura(imagen_servicio.uuid_principal(obj))
