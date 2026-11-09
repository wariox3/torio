from rest_framework import serializers

from contabilidad.models import ConExogenaFormato


class ConExogenaFormatoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConExogenaFormato
        fields = ['id', 'nombre', 'cuantia_menor']
