from rest_framework.routers import DefaultRouter

from turno.views import TurProgramadorViewSet, TurPuestoViewSet

router = DefaultRouter()
router.register(r'programador', TurProgramadorViewSet, basename='programador')
router.register(r'puesto', TurPuestoViewSet, basename='puesto')

urlpatterns = router.urls
