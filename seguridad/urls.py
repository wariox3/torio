from django.urls import path
from rest_framework.routers import DefaultRouter

from seguridad.views import (
    LoginMfaReenviarView,
    LoginMfaView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    SegGrupoViewSet,
    SegMfaViewSet,
    SegPermisoViewSet,
    SegRolViewSet,
    SegUsuarioViewSet,
    SegUsuarioClienteViewSet,
)

router = DefaultRouter()
router.register(r'usuario', SegUsuarioViewSet)
router.register(r'usuario-cliente', SegUsuarioClienteViewSet, basename='usuario-cliente')
router.register(r'rol', SegRolViewSet)
router.register(r'grupo', SegGrupoViewSet)
router.register(r'permiso', SegPermisoViewSet, basename='permiso')
router.register(r'mfa', SegMfaViewSet, basename='mfa')

urlpatterns = [
    path('login/', LoginView.as_view()),
    path('login/mfa/', LoginMfaView.as_view()),
    path('login/mfa/reenviar/', LoginMfaReenviarView.as_view()),
    path('refresh/', RefreshView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('me/', MeView.as_view()),
    *router.urls,
]
