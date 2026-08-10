from django.db import connection
from django.utils import timezone
from django_tenants.utils import get_public_schema_name
from rest_framework import permissions
from rest_framework.permissions import DjangoModelPermissions


class EsMiembroDelTenant(permissions.IsAuthenticated):
    """
    Requiere que el usuario autenticado pertenezca al tenant resuelto por
    `TenantHeaderMiddleware` a partir del header `X-Tenant`. En el schema público
    se omite la validación porque no aplica (allí no hay membresías de tenant).

    Es la única barrera entre contenedores para las vistas que se quedan con las
    permission_classes por defecto: el header lo pone el cliente, así que resolver
    el schema no autoriza nada por sí solo.
    """

    message = 'No tienes acceso a este contenedor.'

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        tenant = connection.tenant
        if tenant is None or tenant.schema_name == get_public_schema_name():
            return True

        from seguridad.models import SegUsuarioCliente
        return SegUsuarioCliente.objects.filter(
            usuario=request.user,
            cliente=tenant,
        ).exists()


class SuscripcionVigente(permissions.BasePermission):
    """
    Bloquea el acceso al tenant cuando su suscripción no existe o está vencida.
    En el schema público se omite para no interrumpir flujos de renovación o
    administración del cliente.

    La fecha se compara contra la fecha actual en la zona horaria del proyecto
    (America/Bogota): una suscripción con fecha_fin = hoy sigue siendo válida
    hasta las 23:59 locales y deja de serlo a las 00:00 del día siguiente.

    Esta comprobación estuvo en un middleware (`SuscripcionActivaMiddleware`),
    que corría antes de que DRF autenticara: cualquier anónimo podía leer el
    estado de suscripción de un contenedor mandando su nombre en X-Tenant. Acá
    corre con el usuario ya resuelto, así que a un no autenticado DRF le
    responde 401 sin revelar nada del contenedor.
    """

    # dict en vez de str para conservar el cuerpo que devolvía el middleware:
    # DRF usa un `message` de tipo dict como body completo de la respuesta, así
    # que el front sigue recibiendo `codigo: 'suscripcion_vencida'`.
    message = {
        'detail': 'La suscripción del contenedor no está vigente.',
        'codigo': 'suscripcion_vencida',
    }

    def has_permission(self, request, view):
        tenant = connection.tenant
        if tenant is None or tenant.schema_name == get_public_schema_name():
            return True

        suscripcion_id = getattr(tenant, 'suscripcion_id', None)
        if suscripcion_id is None:
            return False

        from contenedor.models import CtnSuscripcion
        fecha_fin = CtnSuscripcion.objects.filter(
            pk=suscripcion_id,
        ).values_list('fecha_fin', flat=True).first()

        if fecha_fin is None:
            return False

        return fecha_fin >= timezone.localdate()


class _DjangoModelPermissionsConVer(DjangoModelPermissions):
    """DjangoModelPermissions no exige nada en GET por defecto; acá sí exige `view_<modelo>`."""

    perms_map = {
        **DjangoModelPermissions.perms_map,
        'GET': ['%(app_label)s.view_%(model_name)s'],
    }


class TienePermisoModelo(EsMiembroDelTenant):
    """
    Membresía en el tenant + suscripción vigente + permiso Django (ver/crear/editar/eliminar)
    sobre el modelo del ViewSet, resuelto vía los grupos/permisos del usuario en este tenant
    (UserTenantPermissions, django-tenant-users).
    """

    message = 'No tienes permiso para realizar esta acción sobre este recurso.'

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        suscripcion = SuscripcionVigente()
        if not suscripcion.has_permission(request, view):
            self.message = suscripcion.message
            return False

        if request.user.is_superuser:
            return True

        return _DjangoModelPermissionsConVer().has_permission(request, view)
