from rest_framework import serializers

from general.models import GenMetodoPago


class GenMetodoPagoSerializer(serializers.ModelSerializer):
    campos_filtrables = {'id', 'nombre', 'codigo'}
    ordenamiento_default_lista = ('nombre',)

    class Meta:
        model = GenMetodoPago
        fields = ['id', 'nombre', 'codigo']
