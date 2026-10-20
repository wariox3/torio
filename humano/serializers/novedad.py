from rest_framework import serializers

from humano.models import HumNovedad
from humano.servicios.nomina import NOVEDAD_TIPO_VACACION


class HumNovedadSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato_id', 'novedad_tipo_id', 'prorroga', 'fecha_desde', 'fecha_hasta'}
    select_related_lista = ('contrato', 'contrato__contacto', 'novedad_tipo', 'novedad_referencia')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, allow_null=True)
    contrato_contacto_id = serializers.IntegerField(source='contrato.contacto_id', read_only=True, allow_null=True)
    contrato_contacto_numero_identificacion = serializers.CharField(
        source='contrato.contacto.numero_identificacion', read_only=True, allow_null=True,
    )
    novedad_tipo_nombre = serializers.CharField(source='novedad_tipo.nombre', read_only=True, allow_null=True)

    class Meta:
        model = HumNovedad
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'fecha_desde_periodo',
            'fecha_hasta_periodo',
            'fecha_desde_empresa',
            'fecha_hasta_empresa',
            'fecha_desde_entidad',
            'fecha_hasta_entidad',
            'dias_disfrutados',
            'dias_disfrutados_reales',
            'dias_dinero',
            'pago_disfrute',
            'dias',
            'dias_empresa',
            'dias_entidad',
            'pago_dinero',
            'pago_dia_disfrute',
            'pago_dia_dinero',
            'base_cotizacion_propuesto',
            'base_cotizacion',
            'hora_empresa',
            'hora_entidad',
            'pago_empresa',
            'pago_entidad',
            'total',
            'dias_acumulados',
            'prorroga',
            'detalle',
            'contrato',
            'contrato_nombre',
            'contrato_contacto_id',
            'contrato_contacto_numero_identificacion',
            'novedad_tipo',
            'novedad_tipo_nombre',
            'novedad_referencia',
        ]
        # Todo lo que calcula `servicios.novedad.liquidar`; el resto lo manda el usuario.
        read_only_fields = [
            'id',
            'dias',
            'dias_acumulados',
            'prorroga',
            'base_cotizacion',
            'dias_empresa',
            'hora_empresa',
            'pago_empresa',
            'fecha_desde_empresa',
            'fecha_hasta_empresa',
            'dias_entidad',
            'hora_entidad',
            'pago_entidad',
            'fecha_desde_entidad',
            'fecha_hasta_entidad',
            'pago_dia_disfrute',
            'pago_disfrute',
            'pago_dia_dinero',
            'pago_dinero',
            'total',
        ]

    def validate(self, data):
        def valor(campo):
            if campo in data:
                return data[campo]
            return getattr(self.instance, campo, None)

        fecha_desde = valor('fecha_desde')
        fecha_hasta = valor('fecha_hasta')
        contrato = valor('contrato')
        novedad_tipo = valor('novedad_tipo')
        referencia = valor('novedad_referencia')

        if fecha_desde > fecha_hasta:
            raise serializers.ValidationError('La fecha desde no puede ser mayor que la fecha hasta.')

        if novedad_tipo is None:
            raise serializers.ValidationError('El tipo de novedad es requerido.')

        if novedad_tipo.id == NOVEDAD_TIPO_VACACION and (valor('dias_disfrutados_reales') or 0) <= 0:
            raise serializers.ValidationError('Las vacaciones necesitan días disfrutados reales mayores que cero.')

        if referencia is not None:
            if self.instance and referencia.pk == self.instance.pk:
                raise serializers.ValidationError('Una novedad no puede ser prórroga de sí misma.')
            if referencia.contrato_id != contrato.id:
                raise serializers.ValidationError('La novedad de referencia es de otro contrato.')

        # Un empleado no puede tener dos novedades el mismo día, aunque sean de
        # contratos distintos.
        cruzadas = HumNovedad.objects.filter(
            contrato__contacto_id=contrato.contacto_id,
            fecha_desde__lte=fecha_hasta,
            fecha_hasta__gte=fecha_desde,
        )
        if self.instance:
            cruzadas = cruzadas.exclude(pk=self.instance.pk)
        if cruzadas.exists():
            raise serializers.ValidationError('El rango de fechas se cruza con otra novedad del empleado.')

        return data
