from rest_framework import serializers

from humano.models import HumContrato


class HumContratoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha_desde', 'fecha_hasta', 'salario', 'estado_terminado',
        'auxilio_transporte', 'salario_integral', 'habilitado_turno',
        'contacto', 'contacto__nombre_corto', 'contacto__numero_identificacion',
        'contrato_tipo', 'grupo', 'sucursal', 'cargo',
        'tipo_cotizante', 'subtipo_cotizante', 'riesgo', 'tiempo',
        'tipo_costo', 'motivo_terminacion',
    }
    select_related_lista = (
        'contrato_tipo', 'contacto', 'ciudad_contrato', 'ciudad_labora',
        'grupo', 'sucursal', 'riesgo', 'tipo_cotizante', 'subtipo_cotizante',
        'cargo', 'salud', 'pension', 'entidad_salud', 'entidad_pension',
        'entidad_cesantias', 'entidad_caja', 'tiempo', 'tipo_costo',
        'grupo_contabilidad', 'motivo_terminacion',
    )
    ordenamiento_default_lista = ('-id',)

    contrato_tipo_nombre = serializers.CharField(source='contrato_tipo.nombre', read_only=True, default=None)
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    ciudad_contrato_nombre = serializers.CharField(source='ciudad_contrato.nombre', read_only=True, default=None)
    ciudad_labora_nombre = serializers.CharField(source='ciudad_labora.nombre', read_only=True, default=None)
    grupo_nombre = serializers.CharField(source='grupo.nombre', read_only=True, default=None)
    sucursal_nombre = serializers.CharField(source='sucursal.nombre', read_only=True, default=None)
    riesgo_nombre = serializers.CharField(source='riesgo.nombre', read_only=True, default=None)
    tipo_cotizante_nombre = serializers.CharField(source='tipo_cotizante.nombre', read_only=True, default=None)
    subtipo_cotizante_nombre = serializers.CharField(source='subtipo_cotizante.nombre', read_only=True, default=None)
    cargo_nombre = serializers.CharField(source='cargo.nombre', read_only=True, default=None)
    salud_nombre = serializers.CharField(source='salud.nombre', read_only=True, default=None)
    pension_nombre = serializers.CharField(source='pension.nombre', read_only=True, default=None)
    entidad_salud_nombre = serializers.CharField(source='entidad_salud.nombre', read_only=True, default=None)
    entidad_pension_nombre = serializers.CharField(source='entidad_pension.nombre', read_only=True, default=None)
    entidad_cesantias_nombre = serializers.CharField(source='entidad_cesantias.nombre', read_only=True, default=None)
    entidad_caja_nombre = serializers.CharField(source='entidad_caja.nombre', read_only=True, default=None)
    tiempo_nombre = serializers.CharField(source='tiempo.nombre', read_only=True, default=None)
    tipo_costo_nombre = serializers.CharField(source='tipo_costo.nombre', read_only=True, default=None)
    grupo_contabilidad_nombre = serializers.CharField(source='grupo_contabilidad.nombre', read_only=True, default=None)
    motivo_terminacion_nombre = serializers.CharField(source='motivo_terminacion.nombre', read_only=True, default=None)

    class Meta:
        model = HumContrato
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'salario',
            'auxilio_transporte',
            'salario_integral',
            'estado_terminado',
            'habilitado_turno',
            'comentario',
            'fecha_ultimo_pago',
            'fecha_ultimo_pago_prima',
            'fecha_ultimo_pago_cesantia',
            'fecha_ultimo_pago_vacacion',
            'contrato_tipo',
            'contrato_tipo_nombre',
            'contacto',
            'contacto_nombre',
            'ciudad_contrato',
            'ciudad_contrato_nombre',
            'ciudad_labora',
            'ciudad_labora_nombre',
            'grupo',
            'grupo_nombre',
            'sucursal',
            'sucursal_nombre',
            'riesgo',
            'riesgo_nombre',
            'tipo_cotizante',
            'tipo_cotizante_nombre',
            'subtipo_cotizante',
            'subtipo_cotizante_nombre',
            'cargo',
            'cargo_nombre',
            'salud',
            'salud_nombre',
            'pension',
            'pension_nombre',
            'entidad_salud',
            'entidad_salud_nombre',
            'entidad_pension',
            'entidad_pension_nombre',
            'entidad_cesantias',
            'entidad_cesantias_nombre',
            'entidad_caja',
            'entidad_caja_nombre',
            'tiempo',
            'tiempo_nombre',
            'tipo_costo',
            'tipo_costo_nombre',
            'grupo_contabilidad',
            'grupo_contabilidad_nombre',
            'motivo_terminacion',
            'motivo_terminacion_nombre',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        def valor(campo, default=None):
            return attrs.get(campo, getattr(self.instance, campo, default))

        contacto = valor('contacto')
        fecha_desde = valor('fecha_desde')
        fecha_hasta = valor('fecha_hasta')

        if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
            raise serializers.ValidationError(
                {'detail': 'La fecha hasta no puede ser anterior a la fecha desde.'}
            )

        otros = HumContrato.objects.filter(contacto=contacto)
        if self.instance is not None:
            otros = otros.exclude(pk=self.instance.pk)

        if otros.filter(estado_terminado=False).exists():
            raise serializers.ValidationError(
                {'detail': 'El contacto ya tiene un contrato sin terminar.'}
            )

        # Se cruzan si cada contrato empieza antes de que el otro termine.
        if otros.filter(fecha_desde__lte=fecha_hasta, fecha_hasta__gte=fecha_desde).exists():
            raise serializers.ValidationError(
                {'detail': 'Las fechas se cruzan con otro contrato del contacto.'}
            )

        return attrs
