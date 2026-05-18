from django.urls import path
from rest_framework.routers import DefaultRouter

from general.views import GenContactoViewSet, GenDocumentoViewSet, PruebaView

router = DefaultRouter()
router.register(r'contacto', GenContactoViewSet, basename='contacto')
router.register(r'documento', GenDocumentoViewSet, basename='documento')

urlpatterns = [
    path('prueba/', PruebaView.as_view()),
] + router.urls
