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
)

router = DefaultRouter()
router.register(r'usuario', SegUsuarioViewSet)
router.register(r'rol', SegRolViewSet)
router.register(r'permiso', SegPermisoViewSet)

urlpatterns = [
    path('login/', LoginView.as_view()),
    path('refresh/', RefreshView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('me/', MeView.as_view()),
    *router.urls,
]
