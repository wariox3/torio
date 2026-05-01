from django.db import connection
from rest_framework import permissions


class TienePermiso(permissions.BasePermission):
    """
    Verifica que el usuario autenticado tenga el permiso requerido en el
    tenant actual (resuelto por django-tenants vía Host header).

    Uso simple:
        class FacturaViewSet(ModelViewSet):
            permission_classes = [TienePermiso]
            permiso_requerido = 'factura.crear'

    Uso por acción:
        class FacturaViewSet(ModelViewSet):
            permission_classes = [TienePermiso]
            permisos_por_accion = {
                'list': 'factura.ver',
                'retrieve': 'factura.ver',
                'create': 'factura.crear',
                'update': 'factura.editar',
                'partial_update': 'factura.editar',
                'destroy': 'factura.eliminar',
            }
    """

    message = 'No tienes permiso para realizar esta acción.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        codigo = self._codigo_requerido(view)
        if not codigo:
            return True

        return request.user.tiene_permiso(codigo, connection.tenant)

    def _codigo_requerido(self, view):
        permisos_por_accion = getattr(view, 'permisos_por_accion', None)
        if permisos_por_accion:
            action = getattr(view, 'action', None)
            codigo = permisos_por_accion.get(action)
            if codigo:
                return codigo
        return getattr(view, 'permiso_requerido', None)
