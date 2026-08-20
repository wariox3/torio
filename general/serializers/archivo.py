from rest_framework import serializers

from general.models import GenArchivo, GenArchivoTipo, GenModelo
from general.servicios.archivo import validar_archivo, validar_objeto


class GenArchivoSerializer(serializers.ModelSerializer):
    archivo_tipo_codigo = serializers.CharField(source='archivo_tipo.codigo', read_only=True)
    archivo_tipo_nombre = serializers.CharField(source='archivo_tipo.nombre', read_only=True)
    modelo_app = serializers.CharField(source='modelo.app', read_only=True)
    modelo_clase = serializers.CharField(source='modelo.clase', read_only=True)

    class Meta:
        model = GenArchivo
        fields = [
            'id',
            'fecha',
            'archivo_tipo',
            'archivo_tipo_codigo',
            'archivo_tipo_nombre',
            'modelo',
            'modelo_app',
            'modelo_clase',
            'objeto_id',
            'nombre',
            'tipo',
            'tamano',
            'almacenamiento_id',
            'uuid',
            'url',
        ]
        read_only_fields = fields


class GenArchivoCrearSerializer(serializers.Serializer):
    """
    Valida la entrada de `POST /general/archivo/`.

    Existe aparte de `GenArchivoSerializer` porque ese es de solo lectura: la fila
    no la arma el cliente, la arma `general.servicios.archivo.subir_archivo` con la key
    de B2 y el tenant actual.
    """

    # En multipart todo llega como texto, así que los tres identificadores se
    # declaran enteros explícitamente: sin esto el error por un valor no numérico
    # sale como "tipo incorrecto de clave primaria", que no le dice nada a nadie.
    _NO_ENTERO = {
        'incorrect_type': 'Debe ser un número entero.',
        'invalid': 'Debe ser un número entero.',
    }

    archivo = serializers.FileField()
    modelo = serializers.PrimaryKeyRelatedField(
        queryset=GenModelo.objects.all(),
        error_messages=_NO_ENTERO,
    )
    objeto_id = serializers.IntegerField(
        min_value=1,
        # Tope de un bigint: cualquier pk real cabe, y de paso el valor nunca
        # excede los 50 caracteres que admite la columna.
        max_value=9223372036854775807,
        error_messages=_NO_ENTERO,
    )
    archivo_tipo = serializers.PrimaryKeyRelatedField(
        queryset=GenArchivoTipo.objects.all(),
        default=None,
        error_messages=_NO_ENTERO,
    )

    def to_internal_value(self, data):
        # En multipart un campo presente pero vacío llega como '', que no es lo
        # mismo que omitirlo: sin esto `archivo_tipo` vacío rompe en vez de tomar
        # el default.
        if data.get('archivo_tipo') in ('', None):
            data = data.copy()
            data.pop('archivo_tipo', None)
        return super().to_internal_value(data)

    def validate_archivo(self, archivo):
        try:
            validar_archivo(archivo)
        except ValueError as e:
            raise serializers.ValidationError(str(e))
        return archivo

    def validate(self, datos):
        # A nivel de serializer y no de campo porque hace falta el par completo:
        # `objeto_id` solo se puede verificar contra la tabla que dice `modelo`.
        if 'modelo' in datos and 'objeto_id' in datos:
            try:
                validar_objeto(datos['modelo'], datos['objeto_id'])
            except ValueError as e:
                raise serializers.ValidationError({'objeto_id': str(e)})
        return datos
