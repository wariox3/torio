from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from utilidades.zinc import Zinc


@extend_schema(
    tags=['General'],
    summary='Endpoint de prueba',
    responses=inline_serializer(
        name='PruebaResponse',
        fields={'mensaje': serializers.CharField()},
    ),
)
class PruebaView(APIView):
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return super().get_permissions()

    def get(self, request):
        return Response({'mensaje': 'Hola mundo'})

    @extend_schema(
        summary='Prueba de envío SMS vía Zinc',
        request=inline_serializer(
            name='PruebaSmsRequest',
            fields={
                'numero': serializers.CharField(help_text='10 dígitos sin prefijo'),
                'mensaje': serializers.CharField(),
            },
        ),
        responses=inline_serializer(
            name='PruebaSmsResponse',
            fields={'enviado': serializers.BooleanField()},
        ),
    )
    def post(self, request):
        # Esto es solo una prueba, en producción se debe validar el número y el mensaje adecuadamente
        numero = request.data.get('numero', '')
        mensaje = request.data.get('mensaje', '')
        if not numero or not mensaje:
            return Response(
                {'detail': 'numero y mensaje son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        enviado = Zinc().sms(numero, mensaje)
        return Response({'enviado': enviado})
