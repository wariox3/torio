from rest_framework import serializers

from general.models import GenConfiguracion


class GenConfiguracionSerializer(serializers.ModelSerializer):
    hum_entidad_riesgo_nombre = serializers.CharField(
        source='hum_entidad_riesgo.nombre', read_only=True,
    )

    class Meta:
        model = GenConfiguracion
        fields = [
            'id',
            'gen_uvt',
            'hum_factor',
            'hum_salario_minimo',
            'hum_auxilio_transporte',
            'hum_entidad_riesgo',
            'hum_entidad_riesgo_nombre',
            'gen_empresa_numero_identificacion',
            'gen_empresa_digito_verificacion',
            'gen_empresa_nombre_corto',
            'gen_empresa_razon_social',
            'gen_empresa_direccion',
            'gen_empresa_telefono',
            'gen_empresa_correo',
            'gen_empresa_imagen',
            'gen_empresa_identificacion',
            'gen_empresa_ciudad',
            'gen_empresa_tipo_persona',
            'gen_emitir_automaticamente',
        ]
        # `gen_empresa_logotipo` no está en `fields` a propósito. Es un PNG en base64
    # de decenas de KB —hoy pesa 70 veces más que todos los demás campos juntos—
    # y esta configuración la leen pantallas que solo quieren el UVT o el salario
    # mínimo. Se lee por `GET logotipo/` y se escribe por `cargar-logotipo/`.
    read_only_fields = ['id']
