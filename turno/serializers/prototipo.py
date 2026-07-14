from rest_framework import serializers

from turno.models import TurPrototipo


class TurPrototipoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha', 'fecha_inicio', 'posicion', 'contrato', 'documento_detalle', 'secuencia',
    }
    select_related_lista = (
        'contrato',
        'contrato__contacto',
        'documento_detalle',
        'documento_detalle__puesto',
        'documento_detalle__documento',
        'documento_detalle__documento__documento_tipo',
        'secuencia',
    )
    ordenamiento_default_lista = ('fecha', 'id')

    contrato_nombre = serializers.CharField(
        source='contrato.contacto.nombre_corto', read_only=True, default=None,
    )
    contrato_contacto_numero_identificacion = serializers.CharField(
        source='contrato.contacto.numero_identificacion', read_only=True, default=None,
    )
    documento_numero = serializers.IntegerField(
        source='documento_detalle.documento.numero', read_only=True, default=None,
    )
    documento_fecha = serializers.DateField(
        source='documento_detalle.documento.fecha', read_only=True, default=None,
    )
    documento_documento_tipo_nombre = serializers.CharField(
        source='documento_detalle.documento.documento_tipo.nombre', read_only=True, default=None,
    )
    puesto_nombre = serializers.CharField(
        source='documento_detalle.puesto.nombre', read_only=True, default=None,
    )
    secuencia_nombre = serializers.CharField(
        source='secuencia.nombre', read_only=True, default=None,
    )

    class Meta:
        model = TurPrototipo
        fields = [
            'id',
            'fecha',
            'fecha_inicio',
            'posicion',
            'contrato',
            'contrato_nombre',
            'contrato_contacto_numero_identificacion',
            'documento_detalle',
            'documento_numero',
            'documento_fecha',
            'documento_documento_tipo_nombre',
            'puesto_nombre',
            'secuencia',
            'secuencia_nombre',
        ]
        read_only_fields = ['id']
        # El unique_together lo reporta validate() con `detail`, no con non_field_errors.
        validators = []

    def validate(self, attrs):
        contrato = attrs.get('contrato', getattr(self.instance, 'contrato', None))
        documento_detalle = attrs.get(
            'documento_detalle', getattr(self.instance, 'documento_detalle', None),
        )

        qs = TurPrototipo.objects.filter(
            contrato=contrato, documento_detalle=documento_detalle,
        )
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'detail': 'Ya existe un prototipo para ese contrato y documento detalle.'}
            )

        return attrs
