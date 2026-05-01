from django.urls import path
from rest_framework.routers import DefaultRouter

from seguridad.views import (
    SegLoginView,
    SegLogoutView,
    SegPermisoViewSet,
    SegRefreshView,
    SegRolViewSet,
    SegUsuarioRolViewSet,
    SegUsuarioViewSet,
)

router = DefaultRouter()
router.register(r'usuario', SegUsuarioViewSet)
router.register(r'rol', SegRolViewSet)
router.register(r'permiso', SegPermisoViewSet)
router.register(r'usuario-rol', SegUsuarioRolViewSet)

urlpatterns = [
    path('login/', SegLoginView.as_view()),
    path('refresh/', SegRefreshView.as_view()),
    path('logout/', SegLogoutView.as_view()),
    *router.urls,
]
