from rest_framework.routers import DefaultRouter

from turno.views import (
    TurProgramacionViewSet,
    TurProgramadorViewSet,
    TurPuestoViewSet,
    TurSecuenciaViewSet,
    TurTurnoViewSet,
)

router = DefaultRouter()
router.register(r'programacion', TurProgramacionViewSet, basename='programacion')
router.register(r'programador', TurProgramadorViewSet, basename='programador')
router.register(r'puesto', TurPuestoViewSet, basename='puesto')
router.register(r'secuencia', TurSecuenciaViewSet, basename='secuencia')
router.register(r'turno', TurTurnoViewSet, basename='turno')

urlpatterns = router.urls
