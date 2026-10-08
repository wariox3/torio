from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from general.servicios import factura_electronica as servicio


class EmisorReasignarRequestSerializer(serializers.Serializer):
    emisor = serializers.IntegerField(min_value=1, help_text='Id del emisor en rededoc.')


class AsistenteTerminarRequestSerializer(serializers.Serializer):
    modulo = serializers.ChoiceField(
        choices=tuple(servicio.CAMPO_ASISTENTE_POR_MODULO), help_text='Asistente que se termina.',
    )


class SoftwareConsultarQuerySerializer(serializers.Serializer):
    modulo = serializers.ChoiceField(
        choices=servicio.MODULOS_SOFTWARE, required=False,
        help_text='Filtra el software por módulo; sin él trae todos los del emisor.',
    )


UUID_DIAN = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
UUID_DIAN_INVALIDO = 'Debe ser un UUID de 36 caracteres: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.'


class SoftwareCrearRequestSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=servicio.MODULOS_SOFTWARE, help_text='Operación que habilita el software.')
    identificador = serializers.RegexField(
        UUID_DIAN, error_messages={'invalid': UUID_DIAN_INVALIDO}, help_text='SoftwareID asignado por la DIAN.',
    )
    pin = serializers.CharField(max_length=100, help_text='PIN del software asignado por la DIAN.')
    test_set_id = serializers.RegexField(
        UUID_DIAN, error_messages={'invalid': UUID_DIAN_INVALIDO}, help_text='TestSetId entregado por la DIAN.',
    )



class SoftwareActualizarRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, help_text='Id del software en rededoc.')
    identificador = serializers.RegexField(
        UUID_DIAN, required=False, error_messages={'invalid': UUID_DIAN_INVALIDO},
        help_text='SoftwareID asignado por la DIAN.',
    )
    pin = serializers.CharField(max_length=100, required=False, help_text='PIN del software asignado por la DIAN.')
    test_set_id = serializers.RegexField(
        UUID_DIAN, required=False, error_messages={'invalid': UUID_DIAN_INVALIDO},
        help_text='TestSetId entregado por la DIAN.',
    )

    def validate(self, attrs):
        if not attrs.keys() - {'id'}:
            raise serializers.ValidationError('Envíe al menos uno de: identificador, pin, test_set_id.')
        return attrs


class RecepcionDocumentoQuerySerializer(serializers.Serializer):
    desde = serializers.DateField(required=False, help_text='Fecha de emisión desde (AAAA-MM-DD), inclusive.')
    hasta = serializers.DateField(required=False, help_text='Fecha de emisión hasta (AAAA-MM-DD), inclusive.')
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=servicio.RECEPCION_PAGINA_MAXIMA, default=servicio.RECEPCION_PAGINA,
    )
    search = serializers.CharField(
        max_length=150, required=False,
        help_text='CUFE completo, NIT del proveedor por el comienzo, o número y razón social en cualquier parte.',
    )
    documento_tipo = serializers.ChoiceField(choices=servicio.RECEPCION_DOCUMENTO_TIPOS, required=False)
    proveedor = serializers.RegexField(
        r'^\d{1,20}$', required=False, error_messages={'invalid': 'El NIT va solo con dígitos, sin DV.'},
        help_text='NIT exacto del proveedor, sin DV.',
    )
    correo = serializers.IntegerField(min_value=1, required=False, help_text='Id del correo de recepción.')
    ordering = serializers.ChoiceField(
        choices=[orden for campo in servicio.RECEPCION_ORDENES for orden in (campo, f'-{campo}')],
        required=False, help_text='Con - delante es descendente. Por defecto, los más recientes primero.',
    )

    def validate(self, attrs):
        if attrs.get('desde') and attrs.get('hasta') and attrs['desde'] > attrs['hasta']:
            raise serializers.ValidationError('La fecha desde no puede ser mayor que la fecha hasta.')
        return attrs


@extend_schema(tags=['Electronico'])
class GenElectronicoViewSet(viewsets.GenericViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'], url_path='emisor-crear')
    def emisor_crear(self, request):
        try:
            servicio.emisor_crear()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'], url_path='emisor-consultar')
    def emisor_consultar(self, request):
        try:
            datos = servicio.emisor_consultar()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['patch'], url_path='emisor-actualizar')
    def emisor_actualizar(self, request):
        try:
            datos = servicio.emisor_actualizar()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(request=EmisorReasignarRequestSerializer, responses=None)
    @action(detail=False, methods=['post'], url_path='emisor-reasignar')
    def emisor_reasignar(self, request):
        serializer = EmisorReasignarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            servicio.emisor_reasignar(serializer.validated_data['emisor'])
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'], url_path='emisor-desvincular')
    def emisor_desvincular(self, request):
        try:
            servicio.emisor_desvincular()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

    @extend_schema(request=AsistenteTerminarRequestSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['post'], url_path='asistente-terminar')
    def asistente_terminar(self, request):
        serializer = AsistenteTerminarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campo = servicio.asistente_terminar(serializer.validated_data['modulo'])
        return Response({campo: False}, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'], url_path='certificado-consultar')
    def certificado_consultar(self, request):
        try:
            datos = servicio.certificado_consultar()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'], url_path='certificado-eliminar')
    def certificado_eliminar(self, request):
        try:
            servicio.certificado_eliminar()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

    @extend_schema(parameters=[SoftwareConsultarQuerySerializer], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'], url_path='software-consultar')
    def software_consultar(self, request):
        serializer = SoftwareConsultarQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            datos = servicio.software_consultar(serializer.validated_data.get('modulo'))
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(request=SoftwareCrearRequestSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['post'], url_path='software-crear')
    def software_crear(self, request):
        serializer = SoftwareCrearRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            datos = servicio.software_crear(**serializer.validated_data)
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_201_CREATED)

    @extend_schema(request=SoftwareActualizarRequestSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['patch'], url_path='software-actualizar')
    def software_actualizar(self, request):
        serializer = SoftwareActualizarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)
        software_id = datos.pop('id')
        try:
            respuesta = servicio.software_actualizar(software_id, datos)
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(respuesta, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Documentos recibidos de proveedores',
        description=(
            'La bandeja de recepción del emisor de la empresa en rededoc. El emisor no se '
            'manda: sale de `gen_rededoc_emisor`. Sin `desde` ni `hasta` consulta el mes en '
            'curso. Responde `count`, `page`, `page_size`, el rango aplicado (`desde`, '
            '`hasta`) y `results`; se pagina con `page`.'
        ),
        parameters=[RecepcionDocumentoQuerySerializer],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='recepcion-documento')
    def recepcion_documento(self, request):
        serializer = RecepcionDocumentoQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            datos = servicio.recepcion_documento(serializer.validated_data)
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        request={'multipart/form-data': {
            'type': 'object',
            'properties': {
                'archivo': {'type': 'string', 'format': 'binary'},
                'clave': {'type': 'string'},
            },
            'required': ['archivo', 'clave'],
        }},
        responses=None,
    )
    @action(detail=False, methods=['post'], url_path='certificado-cargar')
    def certificado_cargar(self, request):
        try:
            servicio.certificado_cargar(request.FILES.get('archivo'), request.data.get('clave'))
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)
