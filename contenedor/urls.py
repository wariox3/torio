from rest_framework.routers import DefaultRouter

from contenedor.views import CtnClienteViewSet, CtnMovimientoViewSet

router = DefaultRouter()
router.register(r'cliente', CtnClienteViewSet)
router.register(r'movimiento', CtnMovimientoViewSet, basename='movimiento')

urlpatterns = router.urls
