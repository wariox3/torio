from rest_framework.routers import DefaultRouter

from turno.views import TurProgramadorViewSet, TurPuestoViewSet, TurTurnoViewSet

router = DefaultRouter()
router.register(r'programador', TurProgramadorViewSet, basename='programador')
router.register(r'puesto', TurPuestoViewSet, basename='puesto')
router.register(r'turno', TurTurnoViewSet, basename='turno')

urlpatterns = router.urls
