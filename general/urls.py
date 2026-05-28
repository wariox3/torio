from django.urls import path
from rest_framework.routers import DefaultRouter

from general.views import (
    GenAsesorViewSet,
    GenBancoViewSet,
    GenCiudadViewSet,
    GenContactoViewSet,
    GenCuentaBancoClaseViewSet,
    GenDocumentoViewSet,
    GenIdentificacionViewSet,
    GenLogViewSet,
    GenPlazoPagoViewSet,
    GenPrecioViewSet,
    GenTipoPersonaViewSet,
    PruebaView,
)

router = DefaultRouter()
router.register(r'asesor', GenAsesorViewSet, basename='asesor')
router.register(r'banco', GenBancoViewSet, basename='banco')
router.register(r'ciudad', GenCiudadViewSet, basename='ciudad')
router.register(r'contacto', GenContactoViewSet, basename='contacto')
router.register(r'cuenta-banco-clase', GenCuentaBancoClaseViewSet, basename='cuenta-banco-clase')
router.register(r'documento', GenDocumentoViewSet, basename='documento')
router.register(r'identificacion', GenIdentificacionViewSet, basename='identificacion')
router.register(r'log', GenLogViewSet, basename='log')
router.register(r'plazo-pago', GenPlazoPagoViewSet, basename='plazo-pago')
router.register(r'precio', GenPrecioViewSet, basename='precio')
router.register(r'tipo-persona', GenTipoPersonaViewSet, basename='tipo-persona')

urlpatterns = [
    path('prueba/', PruebaView.as_view()),
] + router.urls
