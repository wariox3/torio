from rest_framework.routers import DefaultRouter

from humano.views import (
    HumAdicionalViewSet,
    HumAporteContratoViewSet,
    HumAporteDetalleViewSet,
    HumAporteEntidadViewSet,
    HumAporteViewSet,
    HumCargoViewSet,
    HumConceptoCuentaViewSet,
    HumConceptoNominaViewSet,
    HumConceptoTipoViewSet,
    HumConceptoViewSet,
    HumConfiguracionAporteViewSet,
    HumConfiguracionProvisionViewSet,
    HumContratoTipoViewSet,
    HumContratoViewSet,
    HumCreditoViewSet,
    HumEntidadViewSet,
    HumGrupoViewSet,
    HumLiquidacionAdicionalViewSet,
    HumLiquidacionViewSet,
    HumMotivoTerminacionViewSet,
    HumNovedadTipoViewSet,
    HumNovedadViewSet,
    HumPagoTipoViewSet,
    HumPensionViewSet,
    HumPeriodoViewSet,
    HumProgramacionDetalleViewSet,
    HumProgramacionViewSet,
    HumRiesgoViewSet,
    HumSaludViewSet,
    HumSubtipoCotizanteViewSet,
    HumSucursalViewSet,
    HumTiempoViewSet,
    HumTipoCostoViewSet,
    HumTipoCotizanteViewSet,
)

router = DefaultRouter()
router.register(r'adicional', HumAdicionalViewSet, basename='adicional')
router.register(r'aporte', HumAporteViewSet, basename='aporte')
router.register(r'aporte-contrato', HumAporteContratoViewSet, basename='aporte-contrato')
router.register(r'aporte-detalle', HumAporteDetalleViewSet, basename='aporte-detalle')
router.register(r'aporte-entidad', HumAporteEntidadViewSet, basename='aporte-entidad')
router.register(r'cargo', HumCargoViewSet, basename='cargo')
router.register(r'concepto', HumConceptoViewSet, basename='concepto')
router.register(r'concepto-cuenta', HumConceptoCuentaViewSet, basename='concepto-cuenta')
router.register(r'concepto-nomina', HumConceptoNominaViewSet, basename='concepto-nomina')
router.register(r'concepto-tipo', HumConceptoTipoViewSet, basename='concepto-tipo')
router.register(r'configuracion-aporte', HumConfiguracionAporteViewSet, basename='configuracion-aporte')
router.register(r'configuracion-provision', HumConfiguracionProvisionViewSet, basename='configuracion-provision')
router.register(r'contrato', HumContratoViewSet, basename='contrato')
router.register(r'contrato-tipo', HumContratoTipoViewSet, basename='contrato-tipo')
router.register(r'credito', HumCreditoViewSet, basename='credito')
router.register(r'entidad', HumEntidadViewSet, basename='entidad')
router.register(r'grupo', HumGrupoViewSet, basename='grupo')
router.register(r'liquidacion', HumLiquidacionViewSet, basename='liquidacion')
router.register(r'liquidacion-adicional', HumLiquidacionAdicionalViewSet, basename='liquidacion-adicional')
router.register(r'motivo-terminacion', HumMotivoTerminacionViewSet, basename='motivo-terminacion')
router.register(r'novedad', HumNovedadViewSet, basename='novedad')
router.register(r'novedad-tipo', HumNovedadTipoViewSet, basename='novedad-tipo')
router.register(r'pago-tipo', HumPagoTipoViewSet, basename='pago-tipo')
router.register(r'pension', HumPensionViewSet, basename='pension')
router.register(r'periodo', HumPeriodoViewSet, basename='periodo')
router.register(r'programacion', HumProgramacionViewSet, basename='programacion')
router.register(r'programacion-detalle', HumProgramacionDetalleViewSet, basename='programacion-detalle')
router.register(r'riesgo', HumRiesgoViewSet, basename='riesgo')
router.register(r'salud', HumSaludViewSet, basename='salud')
router.register(r'subtipo-cotizante', HumSubtipoCotizanteViewSet, basename='subtipo-cotizante')
router.register(r'sucursal', HumSucursalViewSet, basename='sucursal')
router.register(r'tiempo', HumTiempoViewSet, basename='tiempo')
router.register(r'tipo-costo', HumTipoCostoViewSet, basename='tipo-costo')
router.register(r'tipo-cotizante', HumTipoCotizanteViewSet, basename='tipo-cotizante')

urlpatterns = router.urls
