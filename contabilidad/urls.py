from rest_framework.routers import DefaultRouter

from contabilidad.views import (
    ConActivoGrupoViewSet,
    ConActivoViewSet,
    ConCentroCostoViewSet,
    ConComprobanteViewSet,
    ConConciliacionDetalleViewSet,
    ConConciliacionSoporteViewSet,
    ConConciliacionViewSet,
    ConCuentaClaseViewSet,
    ConCuentaCuentaViewSet,
    ConCuentaGrupoViewSet,
    ConCuentaSubcuentaViewSet,
    ConCuentaViewSet,
    ConMetodoDepreciacionViewSet,
    ConMovimientoViewSet,
    ConPeriodoViewSet,
)

router = DefaultRouter()
router.register(r'activo', ConActivoViewSet, basename='activo')
router.register(r'activo-grupo', ConActivoGrupoViewSet, basename='activo-grupo')
router.register(r'centro-costo', ConCentroCostoViewSet, basename='centro-costo')
router.register(r'comprobante', ConComprobanteViewSet, basename='comprobante')
router.register(r'conciliacion', ConConciliacionViewSet, basename='conciliacion')
router.register(r'conciliacion-detalle', ConConciliacionDetalleViewSet, basename='conciliacion-detalle')
router.register(r'conciliacion-soporte', ConConciliacionSoporteViewSet, basename='conciliacion-soporte')
router.register(r'cuenta', ConCuentaViewSet, basename='cuenta')
router.register(r'cuenta-clase', ConCuentaClaseViewSet, basename='cuenta-clase')
router.register(r'cuenta-cuenta', ConCuentaCuentaViewSet, basename='cuenta-cuenta')
router.register(r'cuenta-grupo', ConCuentaGrupoViewSet, basename='cuenta-grupo')
router.register(r'cuenta-subcuenta', ConCuentaSubcuentaViewSet, basename='cuenta-subcuenta')
router.register(r'metodo-depreciacion', ConMetodoDepreciacionViewSet, basename='metodo-depreciacion')
router.register(r'movimiento', ConMovimientoViewSet, basename='movimiento')
router.register(r'periodo', ConPeriodoViewSet, basename='periodo')

urlpatterns = router.urls
