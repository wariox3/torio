from rest_framework.routers import DefaultRouter

from venta.views import VenCajaViewSet, VenTurnoViewSet

router = DefaultRouter()
router.register(r'caja', VenCajaViewSet, basename='caja')
router.register(r'turno', VenTurnoViewSet, basename='turno')

urlpatterns = router.urls
