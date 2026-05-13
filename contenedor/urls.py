from rest_framework.routers import DefaultRouter

from contenedor.views import (
    CtnCiudadViewSet,
    CtnClienteViewSet,
    CtnContactoViewSet,
    CtnEstadoViewSet,
    CtnEventoPagoViewSet,
    CtnIdentificacionViewSet,
    CtnMovimientoViewSet,
    CtnPaisViewSet,
    CtnSuscripcionViewSet,
    CtnSuscripcionTipoViewSet,
)

router = DefaultRouter()
router.register(r'ciudad', CtnCiudadViewSet, basename='ciudad')
router.register(r'cliente', CtnClienteViewSet)
router.register(r'contacto', CtnContactoViewSet, basename='contacto')
router.register(r'estado', CtnEstadoViewSet, basename='estado')
router.register(r'evento-pago', CtnEventoPagoViewSet, basename='evento-pago')
router.register(r'identificacion', CtnIdentificacionViewSet, basename='identificacion')
router.register(r'movimiento', CtnMovimientoViewSet, basename='movimiento')
router.register(r'pais', CtnPaisViewSet, basename='pais')
router.register(r'suscripcion', CtnSuscripcionViewSet, basename='suscripcion')
router.register(r'suscripcion-tipo', CtnSuscripcionTipoViewSet, basename='suscripcion-tipo')

urlpatterns = router.urls
