from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnSolicitud
from contenedor.serializers.solicitud import CtnSolicitudSerializer

_MENSAJE_PENDIENTE = 'El contenedor ya tiene una solicitud pendiente de este tipo.'


@extend_schema(tags=['Solicitud'])
class CtnSolicitudViewSet(viewsets.GenericViewSet):
    serializer_class = CtnSolicitudSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Crear solicitud',
        description=(
            'Un miembro del contenedor le pide algo a torio (`solicitud_tipo`; por '
            'ahora 1, certificado de firma). Nace `pendiente`. Los documentos se '
            'adjuntan después con `POST /contenedor/archivo/`, con `modelo=1` y '
            '`objeto_id` = el `id` que devuelve esta respuesta.\n\n'
            'Un contenedor ajeno responde igual que uno que no existe (400 en '
            '`cliente`). Si ya hay una pendiente del mismo tipo, 409.'
        ),
        responses={
            201: CtnSolicitudSerializer,
            409: OpenApiResponse(
                inline_serializer('CtnSolicitudPendienteSerializer', {'detail': serializers.CharField()}),
                description='Ya hay una solicitud pendiente de ese tipo',
            ),
        },
    )
    def create(self, request):
        serializer = CtnSolicitudSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        pendiente = CtnSolicitud.objects.filter(
            cliente=datos['cliente'],
            solicitud_tipo=datos['solicitud_tipo'],
            estado=CtnSolicitud.ESTADO_PENDIENTE,
        ).exists()
        if pendiente:
            return Response({'detail': _MENSAJE_PENDIENTE}, status=status.HTTP_409_CONFLICT)

        try:
            # Savepoint propio: dos POST a la vez pasan los dos la consulta de
            # arriba, y el índice único frena al segundo.
            with transaction.atomic():
                solicitud = serializer.save(usuario=request.user)
        except IntegrityError:
            return Response({'detail': _MENSAJE_PENDIENTE}, status=status.HTTP_409_CONFLICT)

        return Response(CtnSolicitudSerializer(solicitud).data, status=status.HTTP_201_CREATED)
