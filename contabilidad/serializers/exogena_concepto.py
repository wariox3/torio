from rest_framework import serializers

from contabilidad.models import ConExogenaConcepto


class ConExogenaConceptoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConExogenaConcepto
        fields = ['id', 'codigo', 'nombre', 'formato']
