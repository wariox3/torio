"""
Throttles personalizados que toman en cuenta el tenant activo.
"""
from rest_framework.throttling import UserRateThrottle


class ImportarUsuarioTenantThrottle(UserRateThrottle):
    """
    Throttle para el endpoint `importar`. La llave incluye el schema del tenant
    para que un mismo usuario tenga cupos independientes por tenant.

    Configuración del rate: REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['importar'].
    """

    scope = 'importar'

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        tenant = getattr(request, 'tenant', None)
        schema = getattr(tenant, 'schema_name', 'public')
        return self.cache_format % {
            'scope': self.scope,
            'ident': f'{request.user.pk}:{schema}',
        }
