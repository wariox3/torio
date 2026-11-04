from rest_framework.routers import DefaultRouter

from venta.views import VenCajaViewSet

router = DefaultRouter()
router.register(r'caja', VenCajaViewSet, basename='caja')

urlpatterns = router.urls
