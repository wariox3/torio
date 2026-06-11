from django.urls import path
from rest_framework.routers import DefaultRouter

from general.views import (
    GenArchivoViewSet,
    GenAsesorViewSet,
    GenBancoViewSet,
    GenCiudadViewSet,
    GenConfiguracionViewSet,
    GenContactoViewSet,
    GenCuentaBancoClaseViewSet,
    GenDocumentoDetalleInformeViewSet,
    GenDocumentoDetalleViewSet,
    GenDocumentoViewSet,
    GenIdentificacionViewSet,
    GenImpuestoViewSet,
    GenItemViewSet,
    GenLogViewSet,
    GenModalidadViewSet,
    GenModeloViewSet,
    GenPlazoPagoViewSet,
    GenPrecioViewSet,
    GenResponsabilidadViewSet,
    GenSectorViewSet,
    GenTipoPersonaViewSet,
    PruebaView,
)

router = DefaultRouter()
router.register(r'archivo', GenArchivoViewSet, basename='archivo')
router.register(r'asesor', GenAsesorViewSet, basename='asesor')
router.register(r'banco', GenBancoViewSet, basename='banco')
router.register(r'ciudad', GenCiudadViewSet, basename='ciudad')
router.register(r'configuracion', GenConfiguracionViewSet, basename='configuracion')
router.register(r'contacto', GenContactoViewSet, basename='contacto')
router.register(r'cuenta-banco-clase', GenCuentaBancoClaseViewSet, basename='cuenta-banco-clase')
router.register(r'documento', GenDocumentoViewSet, basename='documento')
router.register(r'documento-detalle', GenDocumentoDetalleViewSet, basename='documento-detalle')
router.register(
    r'documento-detalle-informe',
    GenDocumentoDetalleInformeViewSet,
    basename='documento-detalle-informe',
)
router.register(r'identificacion', GenIdentificacionViewSet, basename='identificacion')
router.register(r'impuesto', GenImpuestoViewSet, basename='impuesto')
router.register(r'item', GenItemViewSet, basename='item')
router.register(r'log', GenLogViewSet, basename='log')
router.register(r'modalidad', GenModalidadViewSet, basename='modalidad')
router.register(r'modelo', GenModeloViewSet, basename='modelo')
router.register(r'plazo-pago', GenPlazoPagoViewSet, basename='plazo-pago')
router.register(r'precio', GenPrecioViewSet, basename='precio')
router.register(r'responsabilidad', GenResponsabilidadViewSet, basename='responsabilidad')
router.register(r'sector', GenSectorViewSet, basename='sector')
router.register(r'tipo-persona', GenTipoPersonaViewSet, basename='tipo-persona')

urlpatterns = [
    path('prueba/', PruebaView.as_view()),
] + router.urls
