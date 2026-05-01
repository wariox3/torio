from rest_framework.routers import DefaultRouter

from contenedor.views import CtnClienteViewSet

router = DefaultRouter()
router.register(r'cliente', CtnClienteViewSet)

urlpatterns = router.urls
