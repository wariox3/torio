from rest_framework import serializers

from general.models import GenItem
from general.serializers.imagen import ImagenPrincipalSerializerMixin


class GenItemSeleccionarSerializer(ImagenPrincipalSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = GenItem
        fields = [
            'id', 'nombre', 'codigo', 'referencia', 'precio',
            'imagen_principal_url', 'imagen_principal_url_miniatura',
        ]
