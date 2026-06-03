from rest_framework.routers import DefaultRouter

from contabilidad.views import ConCentroCostoViewSet, ConCuentaViewSet

router = DefaultRouter()
router.register(r'centro-costo', ConCentroCostoViewSet, basename='centro-costo')
router.register(r'cuenta', ConCuentaViewSet, basename='cuenta')

urlpatterns = router.urls
