from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


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

    def get(self, request):
        return Response({'mensaje': 'Hola mundo'})
