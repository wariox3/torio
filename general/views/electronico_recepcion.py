from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from general.servicios import factura_electronica as servicio


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


class RecepcionCorreoQuerySerializer(serializers.Serializer):
    desde = serializers.DateField(required=False, help_text='Recibido desde (AAAA-MM-DD), inclusive.')
    hasta = serializers.DateField(required=False, help_text='Recibido hasta (AAAA-MM-DD), inclusive.')
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=servicio.RECEPCION_PAGINA_MAXIMA, default=servicio.RECEPCION_PAGINA,
    )
    search = serializers.CharField(max_length=150, required=False, help_text='Remitente, asunto o Message-ID.')
    estado = serializers.ChoiceField(choices=servicio.RECEPCION_CORREO_ESTADOS, required=False)
    origen = serializers.ChoiceField(choices=servicio.RECEPCION_CORREO_ORIGENES, required=False)
    ordering = serializers.ChoiceField(
        choices=[orden for campo in servicio.RECEPCION_CORREO_ORDENES for orden in (campo, f'-{campo}')],
        required=False, help_text='Con - delante es descendente. Por defecto, los más recientes primero.',
    )

    def validate(self, attrs):
        if attrs.get('desde') and attrs.get('hasta') and attrs['desde'] > attrs['hasta']:
            raise serializers.ValidationError('La fecha desde no puede ser mayor que la fecha hasta.')
        return attrs


class RecepcionAdjuntoQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    correo = serializers.IntegerField(min_value=1, required=False, help_text='Id del correo de recepción.')
    documento = serializers.UUIDField(required=False, help_text='Id (uuid) del documento recibido en rededoc.')
    rol = serializers.ChoiceField(
        choices=servicio.RECEPCION_ADJUNTO_ROLES, required=False,
        help_text='xml el recibido, xml_documento el extraído del AttachedDocument, pdf, otro.',
    )
    search = serializers.CharField(max_length=150, required=False, help_text='Busca en el nombre original.')


class RecepcionAdjuntoDescargarQuerySerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text='Id (uuid) del adjunto en rededoc.')


class RecepcionEventoQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=servicio.RECEPCION_PAGINA_MAXIMA, default=servicio.RECEPCION_PAGINA,
    )
    documento = serializers.UUIDField(required=False, help_text='Id (uuid) del documento recibido en rededoc.')
    estado = serializers.ChoiceField(choices=servicio.RECEPCION_EVENTO_ESTADOS, required=False)
    codigo = serializers.ChoiceField(
        choices=servicio.RECEPCION_EVENTO_CODIGOS, required=False,
        help_text='030 acuse, 031 reclamo, 032 recibo del bien o servicio, 033 aceptación.',
    )
    ordering = serializers.ChoiceField(
        choices=[orden for campo in servicio.RECEPCION_EVENTO_ORDENES for orden in (campo, f'-{campo}')],
        required=False, help_text='Con - delante es descendente. Por defecto, los más recientes primero.',
    )


@extend_schema(tags=['ElectronicoRecepcion'])
class GenElectronicoRecepcionViewSet(viewsets.GenericViewSet):
    """
    La recepción de documentos electrónicos del emisor de la empresa en rededoc:
    documentos, correos, eventos RADIAN y adjuntos. En todas, el emisor lo pone el
    back desde `gen_rededoc_emisor`, nunca el front.
    """
    parser_classes = [JSONParser, MultiPartParser, FormParser]

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
    @action(detail=False, methods=['get'], url_path='documento')
    def documento(self, request):
        serializer = RecepcionDocumentoQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            datos = servicio.recepcion_documento(serializer.validated_data)
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Correos recibidos',
        description=(
            'Los correos y cargas manuales que llegaron a la recepción del emisor de la '
            'empresa en rededoc. El emisor no se manda: sale de `gen_rededoc_emisor`. Sin '
            '`desde` ni `hasta` consulta el mes en curso, sobre la fecha de recepción. '
            'Responde `count`, `page`, `page_size`, el rango aplicado y `results`; en cada '
            'correo, `documentos` trae solo los del emisor de la empresa.'
        ),
        parameters=[RecepcionCorreoQuerySerializer],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='correo')
    def correo(self, request):
        serializer = RecepcionCorreoQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            datos = servicio.recepcion_correo(serializer.validated_data)
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Eventos RADIAN de los documentos recibidos',
        description=(
            'Los eventos (030 acuse, 031 reclamo, 032 recibo del bien o servicio, 033 '
            'aceptación) que el emisor de la empresa registró sobre sus documentos recibidos. '
            'El emisor no se manda: sale de `gen_rededoc_emisor`. No hay rango de fechas. '
            'Responde `count`, `page`, `page_size`, `desde` y `hasta` en nulo, y `results`; '
            'en cada evento, `estado` dice si la DIAN lo registró, lo rechazó (motivo en '
            '`respuesta_descripcion`) o no se pudo enviar.'
        ),
        parameters=[RecepcionEventoQuerySerializer],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='evento')
    def evento(self, request):
        serializer = RecepcionEventoQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            datos = servicio.recepcion_evento(serializer.validated_data)
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Adjuntos recibidos',
        description=(
            'Los archivos que llegaron a la recepción del emisor de la empresa: los de cada '
            'documento (`xml`, `xml_documento`, `pdf`) y los demás del correo (`otro`). Se '
            'filtran con `correo`, `documento`, `rol` y `search`. El emisor no se manda: sale '
            'de `gen_rededoc_emisor`, y lo de otra empresa responde vacío. Responde `count`, '
            '`page`, `page_size` (fijo en 10) y `results`; se pagina con `page`.'
        ),
        parameters=[RecepcionAdjuntoQuerySerializer],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='adjunto')
    def adjunto(self, request):
        serializer = RecepcionAdjuntoQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            datos = servicio.recepcion_adjunto(serializer.validated_data)
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Descargar un adjunto recibido',
        description=(
            'El contenido de un adjunto de la recepción del emisor de la empresa, con su '
            'nombre original y siempre como descarga. El emisor no se manda: sale de '
            '`gen_rededoc_emisor`; un adjunto de otra empresa responde 404.'
        ),
        parameters=[RecepcionAdjuntoDescargarQuerySerializer],
        responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['get'], url_path='adjunto-descargar')
    def adjunto_descargar(self, request):
        serializer = RecepcionAdjuntoDescargarQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            contenido, tipo_contenido, disposicion = servicio.recepcion_adjunto_descargar(
                serializer.validated_data['id'],
            )
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        respuesta = HttpResponse(contenido, content_type=tipo_contenido)
        respuesta['Content-Disposition'] = disposicion
        return respuesta

    @extend_schema(
        summary='Cargar documentos recibidos',
        description=(
            'Registra en la recepción del emisor de la empresa los documentos de un ZIP '
            'del proveedor o de un XML suelto (hasta 10 MB). El emisor no se manda: sale '
            'de `gen_rededoc_emisor`. Responde `{creados, repetidos, rechazados}` con 201 '
            'si creó alguno, o 200 si todos ya estaban registrados.'
        ),
        request={'multipart/form-data': {
            'type': 'object',
            'properties': {'archivo': {'type': 'string', 'format': 'binary'}},
            'required': ['archivo'],
        }},
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'], url_path='documento-cargar')
    def documento_cargar(self, request):
        try:
            datos, codigo = servicio.recepcion_documento_cargar(request.FILES.get('archivo'))
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=codigo)
