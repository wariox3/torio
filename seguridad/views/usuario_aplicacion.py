from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from contenedor.models import CtnAplicacion
from seguridad.models import SegUsuarioAplicacion
from seguridad.serializers.usuario_aplicacion import (
    SegUsuarioAplicacionActualizarSerializer,
    SegUsuarioAplicacionSerializer,
)


def _aplicaciones_de(usuario):
    activas = set(
        SegUsuarioAplicacion.objects.filter(usuario=usuario).values_list('aplicacion_id', flat=True)
    )
    return [
        {'aplicacion_id': aplicacion.id, 'aplicacion_nombre': aplicacion.nombre,
         'activa': aplicacion.id in activas}
        for aplicacion in CtnAplicacion.objects.order_by('id')
    ]


@extend_schema(tags=['Usuario-Aplicación'])
class SegUsuarioAplicacionView(APIView):
    """
    Las aplicaciones (módulos) que ve el usuario. Son de la cuenta, no de cada
    contenedor, y las elige el propio usuario: no autorizan nada (eso lo hacen los
    grupos de cada contenedor), solo arman el menú y filtran los pendientes.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Mis aplicaciones',
        description='Todas las aplicaciones del catálogo, con `activa` según el usuario.',
        responses=SegUsuarioAplicacionSerializer(many=True),
    )
    def get(self, request):
        return Response(_aplicaciones_de(request.user))

    @extend_schema(
        summary='Elegir mis aplicaciones',
        description=(
            'Reemplaza las aplicaciones del usuario por las de `aplicaciones` (ids de '
            '`CtnAplicacion`). Una lista vacía las quita todas. Responde como el GET.'
        ),
        request=SegUsuarioAplicacionActualizarSerializer,
        responses=SegUsuarioAplicacionSerializer(many=True),
    )
    def put(self, request):
        aplicaciones = request.data.get('aplicaciones') if isinstance(request.data, dict) else None
        if not isinstance(aplicaciones, list) or not all(
            isinstance(a, int) and not isinstance(a, bool) for a in aplicaciones
        ):
            raise ValidationError({'detail': 'aplicaciones debe ser una lista de ids.'})
        ids = set(aplicaciones)
        inexistentes = ids - set(CtnAplicacion.objects.filter(id__in=ids).values_list('id', flat=True))
        if inexistentes:
            raise ValidationError({
                'detail': 'Aplicaciones inexistentes: ' + ', '.join(map(str, sorted(inexistentes))) + '.',
            })

        with transaction.atomic():
            SegUsuarioAplicacion.objects.filter(usuario=request.user).exclude(aplicacion_id__in=ids).delete()
            SegUsuarioAplicacion.objects.bulk_create(
                [SegUsuarioAplicacion(usuario=request.user, aplicacion_id=i) for i in ids],
                ignore_conflicts=True,
            )
        return Response(_aplicaciones_de(request.user))
