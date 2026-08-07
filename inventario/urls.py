from rest_framework.routers import DefaultRouter

from inventario.views import InvAlmacenViewSet

router = DefaultRouter()
router.register(r'almacen', InvAlmacenViewSet, basename='almacen')

urlpatterns = router.urls
