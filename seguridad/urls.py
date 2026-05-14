from django.urls import path
from rest_framework.routers import DefaultRouter

from seguridad.views import (
    LoginView,
    LogoutView,
    MeView,
    SegPermisoViewSet,
    RefreshView,
    SegRolViewSet,
    SegUsuarioViewSet,
    SegUsuarioClienteViewSet,
)

router = DefaultRouter()
router.register(r'usuario', SegUsuarioViewSet)
router.register(r'usuario-cliente', SegUsuarioClienteViewSet, basename='usuario-cliente')
router.register(r'rol', SegRolViewSet)
router.register(r'permiso', SegPermisoViewSet)

urlpatterns = [
    path('login/', LoginView.as_view()),
    path('refresh/', RefreshView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('me/', MeView.as_view()),
    *router.urls,
]
