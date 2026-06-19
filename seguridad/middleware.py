from datetime import date

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django_tenants.utils import get_public_schema_name, get_tenant_model

from seguridad.contexto import _usuario_actual

try:
    import sentry_sdk
except ImportError:  # Sentry es opcional; sin el paquete el tagging es no-op.
    sentry_sdk = None


class UsuarioActualMiddleware:
    """
    Garantiza el aislamiento del contextvar `_usuario_actual` entre requests:
    lo resetea al inicio y al fin de cada request, así no se filtra el usuario
    de un request a otro en el mismo thread (WSGI sync). El authentication
    class (`SegCookieJWTAuthentication`) es quien efectivamente lo setea
    cuando identifica al usuario del JWT.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _usuario_actual.set(None)
        try:
            return self.get_response(request)
        finally:
            _usuario_actual.reset(token)


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
            self._etiquetar_sentry(get_public_schema_name())
            return self.get_response(request)

        try:
            tenant = self.tenant_model.objects.get(schema_name=slug)
        except self.tenant_model.DoesNotExist:
            self._etiquetar_sentry(slug)
            return JsonResponse(
                {'detail': f'Tenant "{slug}" no existe.'},
                status=404,
            )

        connection.set_tenant(tenant)
        request.tenant = tenant
        self._etiquetar_sentry(tenant.schema_name)
        return self.get_response(request)

    @staticmethod
    def _etiquetar_sentry(schema):
        """Etiqueta el tenant en el scope de Sentry para filtrar errores por cliente."""
        if sentry_sdk is not None:
            sentry_sdk.set_tag('tenant', schema)


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
