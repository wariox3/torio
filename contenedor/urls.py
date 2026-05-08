from rest_framework.routers import DefaultRouter

from contenedor.views import (
    CtnCiudadViewSet,
    CtnClienteViewSet,
    CtnEstadoViewSet,
    CtnMovimientoViewSet,
    CtnPaisViewSet,
)

router = DefaultRouter()
router.register(r'ciudad', CtnCiudadViewSet, basename='ciudad')
router.register(r'cliente', CtnClienteViewSet)
router.register(r'estado', CtnEstadoViewSet, basename='estado')
router.register(r'movimiento', CtnMovimientoViewSet, basename='movimiento')
router.register(r'pais', CtnPaisViewSet, basename='pais')

urlpatterns = router.urls
