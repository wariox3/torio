from django.conf import settings
from django.contrib.auth.models import Permission
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from seguridad.serializers import SegPermisoSerializer

_LIST_PARAMS = [
    OpenApiParameter('app', str, description='Filtrar por app (general, contabilidad, turno, humano)'),
    OpenApiParameter('modelo', str, description='Filtrar por modelo, en minúsculas'),
    OpenApiParameter('accion', str, description='Filtrar por acción: add, change, delete, view'),
    OpenApiParameter('search', str, description='Buscar en el codename y en el nombre'),
]


def apps_asignables():
    """
    `app_label` de las apps cuyos permisos tiene sentido asignar.

    Son las TENANT_APPS propias del proyecto: los permisos de las apps
    compartidas (seguridad, contenedor) no los mira nadie, porque esas vistas se
    gobiernan con IsAuthenticated y reglas de owner, no con permisos de modelo.
    Se excluye `tenant_users`, que es infraestructura de la librería.
    """
    return [
        ruta.rsplit('.', 1)[-1]
        for ruta in settings.TENANT_APPS
        if not ruta.startswith('tenant_users')
    ]


@extend_schema(tags=['Permiso'])
class SegPermisoViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Catálogo de permisos asignables, para poblar el selector del front.

    `auth_permission` vive solo en el schema público y es la misma para todos los
    contenedores, así que esta ruta va en el urlconf público, junto al catálogo
    de grupos. Lo que sí es por tenant es a quién se le asigna, y eso lo hacen
    `agregar-permiso` / `quitar-permiso` de `usuario-cliente-permiso`.

    Solo lectura: los permisos los crea Django en cada `migrate`, a partir de los
    modelos.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SegPermisoSerializer
    queryset = Permission.objects.none()  # el real lo arma get_queryset

    def get_queryset(self):
        qs = Permission.objects.select_related('content_type').filter(
            content_type__app_label__in=apps_asignables(),
        ).order_by('content_type__app_label', 'content_type__model', 'codename')

        parametros = self.request.query_params
        if app := parametros.get('app'):
            qs = qs.filter(content_type__app_label=app)
        if modelo := parametros.get('modelo'):
            qs = qs.filter(content_type__model=modelo)
        if accion := parametros.get('accion'):
            qs = qs.filter(codename__startswith=f'{accion}_')
        if search := parametros.get('search', '').strip():
            qs = qs.filter(codename__icontains=search) | qs.filter(name__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
