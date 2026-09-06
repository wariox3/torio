from rest_framework.routers import DefaultRouter

from inventario.views import InvAlmacenViewSet, InvInformeViewSet

router = DefaultRouter()
router.register(r'almacen', InvAlmacenViewSet, basename='almacen')
router.register(r'informe', InvInformeViewSet, basename='informe')

urlpatterns = router.urls
