from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(tags=['Rededoc'])
class CtnRededocViewSet(viewsets.GenericViewSet):

    @extend_schema(
        summary='Webhook RedEDoc',
        description='Recibe las notificaciones de RedEDoc cuando valida un documento electrónico.',
        request=None,
        responses={200: None},
    )
    @action(
        detail=False,
        methods=['post'],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path='webhook',
    )
    def webhook(self, request):
        return Response(status=status.HTTP_200_OK)
