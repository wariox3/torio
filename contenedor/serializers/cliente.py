from rest_framework import serializers

from contenedor import imagen as imagen_servicio
from contenedor.models import CtnCliente, CtnDominio
from seguridad.models import SegUsuarioCliente
from utilidades.telefono import CampoTelefono


class CtnClienteSerializer(serializers.ModelSerializer):
    """
    El plan no se elige al crear el contenedor: todo tenant nuevo arranca en la
    suscripción de prueba que fija `CtnClienteViewSet.create`. Cambiarlo es cosa de
    `/contenedor/suscripcion/`, que sí valida tipo y frecuencia entre sí.
    """

    celular = CampoTelefono(label='Celular', max_length=20)
    imagen = serializers.SerializerMethodField()
    imagen_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = CtnCliente
        fields = [
            'id', 'schema_name', 'nombre', 'celular', 'correo', 'activo', 'estado',
            'fecha_creacion', 'imagen', 'imagen_thumbnail',
        ]
        read_only_fields = ['id', 'activo', 'estado', 'fecha_creacion']

    def get_imagen(self, obj) -> str | None:
        return imagen_servicio.url_original(obj)

    def get_imagen_thumbnail(self, obj) -> str | None:
        return imagen_servicio.url_thumbnail(obj)


class CtnClienteActualizarSerializer(serializers.ModelSerializer):
    celular = CampoTelefono(label='Celular', max_length=20)

    class Meta:
        model = CtnCliente
        fields = ['nombre', 'correo', 'celular']


class CtnClienteListaUsuarioSerializer(serializers.ModelSerializer):
    cliente_id = serializers.IntegerField(source='cliente.id', read_only=True)
    schema_name = serializers.CharField(source='cliente.schema_name', read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    activo = serializers.BooleanField(source='cliente.activo', read_only=True)
    # Un contenedor en `creando` o `error` también aparece en la lista: el front
    # lo muestra con su estado en vez de dejar entrar.
    estado = serializers.CharField(source='cliente.estado', read_only=True)
    dominio = serializers.SerializerMethodField()
    cliente_fecha_ultima_conexion = serializers.DateTimeField(
        source='cliente.fecha_ultima_conexion', read_only=True,
    )
    cliente_imagen = serializers.SerializerMethodField()
    cliente_imagen_thumbnail = serializers.SerializerMethodField()
    suscripcion_id = serializers.IntegerField(source='cliente.suscripcion.id', read_only=True)
    suscripcion_fecha_fin = serializers.DateField(source='cliente.suscripcion.fecha_fin', read_only=True)
    suscripcion_frecuencia = serializers.CharField(source='cliente.suscripcion.frecuencia', read_only=True)
    suscripcion_suscripcion_tipo_nombre = serializers.CharField(
        source='cliente.suscripcion.suscripcion_tipo.nombre', read_only=True,
    )

    class Meta:
        model = SegUsuarioCliente
        # `id` es el de la membresía (`SegUsuarioCliente`), el que espera
        # `DELETE /seguridad/usuario-cliente/<id>/` para salirse del contenedor. El
        # del contenedor es `cliente_id`.
        fields = [
            'id', 'cliente_id', 'schema_name', 'cliente_nombre', 'activo', 'estado', 'dominio',
            'cliente_fecha_ultima_conexion', 'cliente_imagen', 'cliente_imagen_thumbnail',
            'suscripcion_id', 'suscripcion_fecha_fin', 'suscripcion_frecuencia',
            'suscripcion_suscripcion_tipo_nombre',
            'propietario',
            'acceso_venta', 'acceso_compra', 'acceso_tesoreria', 'acceso_cartera',
            'acceso_inventario', 'acceso_humano', 'acceso_contabilidad',
            'acceso_turno',
        ]

    def get_cliente_imagen(self, obj) -> str | None:
        return imagen_servicio.url_original(obj.cliente)

    def get_cliente_imagen_thumbnail(self, obj) -> str | None:
        return imagen_servicio.url_thumbnail(obj.cliente)

    def get_dominio(self, obj):
        dominios = getattr(obj.cliente, '_dominio_primario', None)
        if dominios is not None:
            return dominios[0].domain if dominios else None
        dominio = CtnDominio.objects.filter(tenant=obj.cliente, is_primary=True).first()
        return dominio.domain if dominio else None


class CtnClienteAdministrarSerializer(serializers.ModelSerializer):
    """
    Un contenedor visto desde el panel del staff: todos, no solo los del usuario.

    `usuarios` y `suscripcion_vigente` llegan anotados desde la vista, para no
    hacer una consulta por fila.
    """

    dominio = serializers.SerializerMethodField()
    imagen = serializers.SerializerMethodField()
    imagen_thumbnail = serializers.SerializerMethodField()
    owner_email = serializers.CharField(source='owner.email', read_only=True, default=None)
    owner_nombre_corto = serializers.CharField(source='owner.nombre_corto', read_only=True, default=None)
    suscripcion_fecha_fin = serializers.DateField(
        source='suscripcion.fecha_fin', read_only=True, default=None,
    )
    suscripcion_frecuencia = serializers.CharField(
        source='suscripcion.frecuencia', read_only=True, default=None,
    )
    suscripcion_suscripcion_tipo_nombre = serializers.CharField(
        source='suscripcion.suscripcion_tipo.nombre', read_only=True, default=None,
    )
    suscripcion_vigente = serializers.BooleanField(read_only=True)
    usuarios = serializers.IntegerField(read_only=True)

    class Meta:
        model = CtnCliente
        fields = [
            'id', 'schema_name', 'nombre', 'correo', 'celular', 'activo', 'estado', 'dominio',
            'fecha_creacion', 'fecha_ultima_conexion', 'imagen', 'imagen_thumbnail',
            'owner_id', 'owner_email', 'owner_nombre_corto',
            'suscripcion_id', 'suscripcion_fecha_fin', 'suscripcion_frecuencia',
            'suscripcion_suscripcion_tipo_nombre', 'suscripcion_vigente',
            'usuarios',
        ]
        read_only_fields = fields

    def get_dominio(self, obj) -> str | None:
        dominios = getattr(obj, '_dominio_primario', None)
        if dominios is not None:
            return dominios[0].domain if dominios else None
        dominio = CtnDominio.objects.filter(tenant=obj, is_primary=True).first()
        return dominio.domain if dominio else None

    def get_imagen(self, obj) -> str | None:
        return imagen_servicio.url_original(obj)

    def get_imagen_thumbnail(self, obj) -> str | None:
        return imagen_servicio.url_thumbnail(obj)
