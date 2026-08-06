from django.contrib.auth.models import Permission
from rest_framework import serializers


class SegPermisoSerializer(serializers.ModelSerializer):
    """
    Permiso de Django, desglosado para que el front no tenga que parsear el
    `codename`.

    `nombre` es el texto que genera Django ("Can add gen contacto"); sirve de
    apoyo, pero para mostrar al usuario suele convenir componerlo desde `accion`
    y `modelo`.
    """

    app = serializers.CharField(source='content_type.app_label', read_only=True)
    modelo = serializers.CharField(source='content_type.model', read_only=True)
    # `ContentType.name` devuelve el `verbose_name` del modelo ('Activo'), no el
    # nombre de la tabla con prefijo de app ('conactivo'). Si el modelo ya no
    # existiera, Django cae de vuelta al nombre técnico en vez de romper.
    modelo_label = serializers.CharField(source='content_type.name', read_only=True)
    nombre = serializers.CharField(source='name', read_only=True)
    accion = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ['id', 'app', 'modelo', 'modelo_label', 'accion', 'codename', 'nombre']
        read_only_fields = fields

    def get_accion(self, obj):
        # El codename es '<accion>_<modelo>'. Si alguien define uno a medida que
        # no siga esa forma, se devuelve completo en vez de recortarlo mal.
        return obj.codename.removesuffix(f'_{obj.content_type.model}')
