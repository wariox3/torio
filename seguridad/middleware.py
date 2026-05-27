from datetime import date

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django_tenants.utils import get_public_schema_name, get_tenant_model


class TenantHeaderMiddleware:
    """
    Resuelve el tenant desde el header X-Tenant en vez del Host.
    Sin header (o con el nombre del schema público) opera en el schema
    público — eso cubre login, registro, refresh, recuperar clave, swagger
    y admin. Con header válido, setea connection.tenant y deja que las
    permissions (EsMiembroDelTenant) validen la membresía del usuario.
    """

    HEADER = 'X-Tenant'

    def __init__(self, get_response):
        self.get_response = get_response
        self.tenant_model = get_tenant_model()

    def __call__(self, request):
        slug = request.headers.get(self.HEADER)

        if not slug or slug == get_public_schema_name():
            connection.set_schema_to_public()
            request.tenant = connection.tenant
            request.urlconf = settings.PUBLIC_SCHEMA_URLCONF
            return self.get_response(request)

        try:
            tenant = self.tenant_model.objects.get(schema_name=slug)
        except self.tenant_model.DoesNotExist:
            return JsonResponse(
                {'detail': f'Tenant "{slug}" no existe.'},
                status=404,
            )

        connection.set_tenant(tenant)
        request.tenant = tenant
        return self.get_response(request)


class SuscripcionActivaMiddleware:
    """
    Bloquea las peticiones a tenants cuyo cliente no tenga suscripción
    vigente. Debe ir DESPUÉS de TenantHeaderMiddleware para tener
    disponible request.tenant. En el schema público no hace nada.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            return self.get_response(request)

        suscripcion = tenant.suscripcion
        if (
            suscripcion is None
            or suscripcion.fecha_fin is None
            or suscripcion.fecha_fin < date.today()
        ):
            return JsonResponse(
                {
                    'detail': 'La suscripción del cliente está vencida.',
                    'codigo': 'suscripcion_vencida',
                },
                status=403,
            )

        return self.get_response(request)
