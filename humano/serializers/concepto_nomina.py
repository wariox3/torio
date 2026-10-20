from rest_framework import serializers

from humano.models import HumConcepto, HumConceptoNomina


class HumConceptoNominaSerializer(serializers.ModelSerializer):
    """
    Lista y edición de los conceptos de nómina. Es un catálogo: el id y el nombre
    los fija torio y el cliente solo elige a qué `concepto` apunta cada uno (con
    eso la nómina arma sus líneas). El JSON del catálogo va con `solo_crear` para
    que `cargar_datos_tenant` no pise esa elección.
    """

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'nombre', 'concepto_id'}
    select_related_lista = ('concepto',)
    ordenamiento_default_lista = ('id',)

    # Obligatorio: la nómina no puede liquidar un concepto de nómina sin concepto.
    concepto = serializers.PrimaryKeyRelatedField(queryset=HumConcepto.objects.all())
    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, allow_null=True)

    class Meta:
        model = HumConceptoNomina
        fields = ['id', 'nombre', 'concepto', 'concepto_nombre']
        read_only_fields = ['id', 'nombre']


class HumConceptoNominaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConceptoNomina
        fields = ['id', 'nombre', 'concepto']
