from rest_framework import serializers

from inventario.models import InvAlmacen


class InvAlmacenSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {'id', 'nombre'}
    ordenamiento_default_lista = ('-id',)

    class Meta:
        model = InvAlmacen
        fields = ['id', 'nombre']
        read_only_fields = ['id']
