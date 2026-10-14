from rest_framework import serializers

from contenedor import archivo as archivo_servicio
from contenedor.models import CtnArchivo, CtnArchivoTipo, CtnModelo


class CtnArchivoSerializer(serializers.ModelSerializer):
    archivo_tipo_codigo = serializers.CharField(source='archivo_tipo.codigo', read_only=True)
    archivo_tipo_nombre = serializers.CharField(source='archivo_tipo.nombre', read_only=True)
    modelo_clase = serializers.CharField(source='modelo.clase', read_only=True)

    class Meta:
        model = CtnArchivo
        # Sin `almacenamiento_id`: la key de B2 no le sirve al front, y el bucket es
        # privado.
        fields = [
            'id', 'fecha', 'cliente', 'modelo', 'modelo_clase', 'objeto_id',
            'archivo_tipo', 'archivo_tipo_codigo', 'archivo_tipo_nombre',
            'nombre', 'tipo', 'tamano', 'uuid',
        ]
        read_only_fields = fields


class CtnArchivoCrearSerializer(serializers.Serializer):
    """
    Valida la entrada de `POST /contenedor/archivo/`. Deja el registro dueño en
    `objeto` para que la vista revise la membresía sin volver a buscarlo.
    """

    # En multipart todo llega como texto: sin esto un valor no numérico sale como
    # "tipo incorrecto de clave primaria", que no le dice nada a nadie.
    _NO_ENTERO = {
        'incorrect_type': 'Debe ser un número entero.',
        'invalid': 'Debe ser un número entero.',
    }

    archivo = serializers.FileField()
    modelo = serializers.PrimaryKeyRelatedField(
        queryset=CtnModelo.objects.all(), error_messages=_NO_ENTERO,
    )
    objeto_id = serializers.IntegerField(
        min_value=1, max_value=9223372036854775807, error_messages=_NO_ENTERO,
    )
    archivo_tipo = serializers.PrimaryKeyRelatedField(
        queryset=CtnArchivoTipo.objects.all(), error_messages=_NO_ENTERO,
    )

    def validate_archivo(self, archivo):
        try:
            archivo_servicio.validar_archivo(archivo)
        except ValueError as e:
            raise serializers.ValidationError(str(e))
        return archivo

    def validate(self, datos):
        try:
            datos['objeto'] = archivo_servicio.buscar_objeto(datos['modelo'], datos['objeto_id'])
        except ValueError as e:
            raise serializers.ValidationError({'objeto_id': str(e)})
        return datos
