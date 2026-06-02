from rest_framework.routers import DefaultRouter

from contabilidad.views import ConCuentaViewSet

router = DefaultRouter()
router.register(r'cuenta', ConCuentaViewSet, basename='cuenta')

urlpatterns = router.urls
