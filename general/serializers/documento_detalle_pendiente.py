from rest_framework import serializers

from general.models import GenDocumentoDetalle


class GenDocumentoDetallePendienteSerializer(serializers.ModelSerializer):
    """
    Serializer liviano (plano, solo lectura) para el listado de detalles con saldo
    pendiente (> 0). La invariante `pendiente > 0` la garantiza el ViewSet en
    `get_queryset`; aquí solo se define el contrato de columnas y la whitelist de
    filtros/orden que consume `FiltrosDinamicosMixin`.

    `contacto` proviene del documento (el cliente que adeuda — lógica de cartera).
    """

    campos_filtrables = {
        'id',
        'documento_id',
        'item_id',
        'pendiente',
        'documento__numero',
        'documento__fecha',
        'documento__contacto_id',
    }
    select_related_lista = ('documento', 'documento__contacto', 'item')
    ordenamiento_default_lista = ('-documento__fecha', '-id')

    numero = serializers.IntegerField(source='documento.numero', read_only=True)
    fecha = serializers.DateField(source='documento.fecha', read_only=True)
    contacto_id = serializers.IntegerField(source='documento.contacto_id', read_only=True)
    contacto_nombre = serializers.CharField(
        source='documento.contacto.nombre_corto', read_only=True, default=None,
    )
    item_nombre = serializers.CharField(source='item.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumentoDetalle
        fields = [
            'id',
            'documento',
            'numero',
            'fecha',
            'contacto_id',
            'contacto_nombre',
            'item_id',
            'item_nombre',
            'cantidad',
            'precio',
            'total',
            'afectado',
            'pendiente',
        ]
